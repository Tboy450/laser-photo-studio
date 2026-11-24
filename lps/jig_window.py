"""Pocket placement and motion review for the tin jig, entirely offline."""
import copy
import queue
import threading
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from . import jig_project, outlines, simulate, tinjig
from .dialogs import FormDialog


class JigWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Flush tin jig · Laser Photo Studio")
        self.geometry("820x570")
        self.project = jig_project.Project(tinjig.flush_layout())
        self.index = 0
        self.file = None
        self.dirty = False
        self.checked = []
        self.check_stop = None
        self.carton_travel = None
        self.status = tk.StringVar(value="9 tins in three flush rows. 2 1/16 in outside diameter (52.3875 mm). "
                                         "Use Flush spacing to enter another diameter.")
        self.pocket_label = tk.StringVar()
        self.map_mode = tk.StringVar(value="Burn map")
        bar = ttk.Frame(self, padding=5)
        bar.pack(fill="x")
        for name, action in (("New layout…", self.new), ("Open jig…", self.open), ("Save jig", self.save),
                             ("Save as…", lambda: self.save(True)), ("Flush spacing…", self.flush_spacing),
                             ("Layout…", self.edit_layout)):
            ttk.Button(bar, text=name, command=action).pack(side="left", padx=2)
        self.canvas = tk.Canvas(self, background="#20262b", height=210, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        footer = ttk.Frame(self, padding=6)
        footer.pack(fill="x")
        header = ttk.Frame(footer)
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.pocket_label).pack(side="left")
        ttk.Button(header, text="Edit pocket…", command=self.edit_pocket).pack(side="right")
        self.layers = tk.Listbox(footer, height=3, exportselection=False)
        self.layers.pack(fill="x", pady=3)
        self.layers.bind("<<ListboxSelect>>", lambda _: self.display())
        row = ttk.Frame(footer)
        row.pack(fill="x")
        for name, action in (("Add job…", self.add), ("Use current checked job", self.add_current),
                             ("Remove layer", self.remove), ("Check pocket", self.check)):
            ttk.Button(row, text=name, command=action).pack(side="left", padx=1)
        switch = ttk.Combobox(row, textvariable=self.map_mode, state="readonly", width=14,
                              values=["Burn map", "Image circle", "Travel"])
        switch.pack(side="right")
        switch.bind("<<ComboboxSelected>>", lambda _: self.display())
        carton = ttk.Frame(footer)
        carton.pack(fill="x", pady=2)
        ttk.Button(carton, text="Copy layers to empty pockets", command=self.fill_empty).pack(side="left")
        ttk.Button(carton, text="Check jig travel", command=lambda: self.check(whole=True)).pack(side="left", padx=2)
        ttk.Button(carton, text="Open selected layer in Check", command=self.open_selected).pack(side="right")
        ttk.Label(footer, textvariable=self.status, wraplength=720, justify="left").pack(anchor="w", pady=4)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def close(self):
        if self.may_replace():
            self.cancel_check()
            self.destroy()

    def may_replace(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Tin jig", "Save your jig changes?", parent=self)
        return answer is False or (answer is True and self.save())

    def save(self, choose=False):
        path = self.file if not choose else None
        path = path or filedialog.asksaveasfilename(parent=self, title="Save tin jig", defaultextension=".lpsjig",
                                                    filetypes=[("Studio tin jig", "*.lpsjig")])
        if not path:
            return False
        try:
            self.project.save(path)
        except OSError as exc:
            self.status.set(str(exc))
            return False
        self.file, self.dirty = Path(path), False
        self.title(f"Tin jig · {self.file.name}")
        self.status.set(f"Saved {self.file}")
        return True

    def open(self):
        path = filedialog.askopenfilename(parent=self, title="Open tin jig", filetypes=[("Studio tin jig", "*.lpsjig")])
        if not path:
            return
        try:
            project = jig_project.Project.read(path)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.status.set(f"Could not open the jig. {exc}")
            return
        if self.may_replace():
            self.project, self.file, self.index, self.dirty = project, Path(path), 0, False
            self.title(f"Tin jig · {self.file.name}")
            self.refresh("Layout opened. Check a pocket to verify its saved layers.")

    def new(self):
        picker = tk.Toplevel(self)
        picker.title("New tin layout")
        selected = tk.StringVar(picker, value=self.project.layout.name if self.project.layout.name in tinjig.PRESETS else "6 (3 x 2)")
        ttk.Combobox(picker, values=list(tinjig.PRESETS), textvariable=selected, state="readonly", width=36).pack(padx=10,pady=8)
        def create():
            name = selected.get()
            picker.destroy()
            if self.may_replace():
                diameter = self.project.layout.outside_diameter or self.project.layout.pitch_x
                self.project = jig_project.Project(tinjig.flush_layout(name, diameter))
                self.file, self.index, self.dirty = None, 0, True
                self.title("Tin jig · New layout")
                self.refresh(f"Flush rows. Tin outside diameter and both centre spacings are {diameter:g} mm.")
        ttk.Button(picker, text="Create layout", command=create).pack(pady=6)
        picker.transient(self)
        picker.grab_set()

    def flush_spacing(self):
        layout = self.project.layout
        diameter = layout.outside_diameter or layout.pitch_x
        values = FormDialog(self, "Flush tin spacing",
            [("diameter","Tin outside diameter (mm)",diameter,"float")],
            intro="Touching tins in straight rows use one outside diameter between centres in both directions. "
                  "Existing individual pocket adjustments are retained.").result
        if values:
            try:
                if any(s.done for s in layout.slots):
                    raise ValueError("Completed pockets lock the layout.")
                d = values["diameter"]
                self.project.layout = tinjig.Layout.from_dict(dict(layout.to_dict(), outside_diameter=d,
                    pitch_x=d, pitch_y=d, stagger_x=0))
                self.changed()
                self.status.set(f"Flush spacing set to {d:g} mm on both axes.")
            except ValueError as exc:
                self.status.set(str(exc))

    def edit_layout(self):
        layout = self.project.layout
        fields = [("pitch_x", "Horizontal centre spacing (mm)", layout.pitch_x, "float"),
                  ("pitch_y", "Vertical centre spacing (mm)", layout.pitch_y, "float"),
                  ("group_dx", "Whole jig X offset (mm)", layout.group_dx, "float"),
                  ("group_dy", "Whole jig Y offset (mm)", layout.group_dy, "float"),
                  ("stagger_x", "Every second row X offset (mm)", layout.stagger_x, "float"),
                  ("zero", "Shared job zero", layout.zero, ["slot1", "centre"]),
                  ("flip_alternate_rows", "Turn pictures 180° in every second row", layout.flip_alternate_rows, "bool")]
        values = FormDialog(self, "Layout", fields, intro="Job zero stays at the saved reference. Measure centre to centre.").result
        if values:
            try:
                updated = tinjig.Layout.from_dict(dict(layout.to_dict(), **values))
                if any(s.done for s in layout.slots):
                    raise ValueError("Completed pockets lock the layout.")
                self.project.layout = updated
                self.changed()
            except ValueError as exc:
                self.status.set(str(exc))

    def edit_pocket(self):
        layout = self.project.layout
        slot = layout.slots[self.index]
        x,y = layout.centre(self.index)
        fields = [("enabled", "Include this pocket in the layout", slot.enabled, "bool"),
                  ("x","Pocket centre X from jig zero (mm)",x,"float"),("y","Pocket centre Y from jig zero (mm)",y,"float"),
                  ("angle","Picture clockwise (degrees)",90*layout.rotation(self.index),["0","90","180","270"])]
        values = FormDialog(self,"Edit pocket",fields,intro="These coordinates and orientation apply to every layer in this pocket.").result
        if values:
            try:
                angle=int(values["angle"])
                if angle not in (0,90,180,270):
                    raise ValueError("Use 0, 90, 180 or 270 degrees.")
                layout.nudge([self.index],values["x"]-x,values["y"]-y)
                slot.enabled = values["enabled"]
                slot.rot = (angle//90 - (layout.rotation(self.index)-slot.rot)) % 4
                self.changed()
            except ValueError as exc:
                self.status.set(str(exc))

    def add_path(self, path):
        try:
            slot = self.project.layout.slots[self.index]
            if slot.done or not slot.enabled:
                raise ValueError("Choose an enabled, unfinished pocket.")
            layer = jig_project.Layer.checked(path)
            items = self.project.layers.setdefault(self.index, [])
            if layer in items:
                raise ValueError("This layer is already assigned to this pocket.")
            items.append(layer)
            self.changed()
        except Exception as exc:
            self.status.set(f"Could not add the layer. {exc}")

    def add(self):
        path = filedialog.askopenfilename(parent=self, title="Assign a saved Studio job",
            initialdir=self.app._picker_folder("job"), filetypes=[("Studio picture job","*.lpsjob job.json")])
        if path:
            self.add_path(path)

    def add_current(self):
        try:
            folder = self.app.save_current_job(quiet=True) if self.app.picture is not None else None
        except OSError as exc:
            self.status.set(f"Could not save the current picture job. {exc}")
            return
        if folder:
            self.add_path(folder)
        else:
            self.status.set("Open a picture, choose its material and size, then check the job in Step 4.")

    def remove(self):
        selected = self.layers.curselection()
        if selected:
            self.project.layers[self.index].pop(selected[0])
            self.changed()

    def fill_empty(self):
        layers = self.project.layers.get(self.index)
        empty = [i for i in self.project.layout.queue() if not self.project.layers.get(i)]
        if not layers or not empty:
            self.status.set("Assign a layer to the selected pocket and leave at least one other pocket empty.")
            return
        if messagebox.askyesno("Copy pocket layers", f"Copy these {len(layers)} layer(s) into {len(empty)} empty pockets?", parent=self):
            for i in empty:
                self.project.layers[i] = layers.copy()
            self.changed()

    def changed(self):
        self.dirty = True
        self.refresh("Jig edited. Check this pocket for updated marks and travel.")

    def open_selected(self):
        selected = self.layers.curselection()
        if not selected or not self.checked:
            self.status.set("Choose a layer and check its pocket first.")
            return
        if self.app._picture_job_in_use():
            self.status.set("Finish the current Studio operation before opening another job.")
            return
        if (self.dirty or self.file is None) and not self.save():
            return
        try:
            folder = self.project.prepare(self.file, self.index, selected[0])
            if self.app.open_saved_job(folder):
                self.app.goto(3)
                self.app.root.lift()
                zero = "pocket 1's centre" if self.project.layout.zero == "slot1" else "the jig centre"
                self.app.say(f"Pocket {self.index+1} loaded. Use {zero} as shared jig zero. Verify travel before Start.", "ok")
        except Exception as exc:
            self.status.set(f"Could not prepare this pocket. {exc}")

    def select(self, i):
        self.index = i
        self.refresh("Choose Check pocket to see its layers and travel from jig zero.")

    def refresh(self, message=None):
        self.cancel_check()
        self.carton_travel = None
        self.checked = []
        self.layers.delete(0, "end")
        for n,layer in enumerate(self.project.layers.get(self.index, []), 1):
            self.layers.insert("end", f"{n}. {layer.name}")
        if self.layers.size():
            self.layers.select_set(0)
        x,y = self.project.layout.centre(self.index)
        layout = self.project.layout
        datum = "pocket 1" if layout.zero == "slot1" else "jig centre"
        state = "" if layout.slots[self.index].enabled else " (off)"
        self.pocket_label.set(f"Pocket {self.index+1}{state} · X {x:g}, Y {y:g} mm from {datum} · picture {90*layout.rotation(self.index)}°")
        if message:
            self.status.set(message)
        self.draw()

    def cancel_check(self):
        if self.check_stop is not None:
            self.check_stop.set()
            self.check_stop = None

    def check(self, whole=False):
        self.cancel_check()
        stop = self.check_stop = threading.Event()
        events = queue.SimpleQueue()
        project, selected = copy.deepcopy(self.project), self.index
        self.checked, self.carton_travel = [], None
        self.draw()
        self.status.set("Checking pocket placements and command travel offline…")
        def work():
            read = lru_cache(maxsize=4)(jig_project.Layer.read)
            selected_jobs, bounds = [], [0., 0., 0., 0.]
            pockets = ([i for i in project.layout.enabled() if project.layers.get(i)] if whole else [selected])
            warnings = set()
            try:
                if not pockets:
                    raise ValueError("Assign a job to at least one pocket first.")
                for i in pockets:
                    if stop.is_set():
                        return
                    plans = project.check(i, read)
                    if i == selected:
                        selected_jobs = plans
                    for job, report, _ in plans:
                        t = report["travel"]
                        bounds = [min(bounds[0], t[0]), min(bounds[1], t[1]),
                                  max(bounds[2], t[2]), max(bounds[3], t[3])]
                        if project.neighbouring_pockets(i, job.piece["w"]):
                            warnings.add(i+1)
                events.put((selected_jobs, bounds, len(pockets), sorted(warnings), None))
            except Exception as exc:
                events.put(([], None, 0, [], str(exc)))
        def finish():
            if stop.is_set():
                return
            try:
                placed, bounds, count, warnings, error = events.get_nowait()
            except queue.Empty:
                self.after(80, finish)
                return
            self.check_stop = None
            self.checked = placed
            if error:
                self.status.set(f"Check stopped. {error}")
            elif whole:
                self.carton_travel = bounds
                self.map_mode.set("Travel")
                a,b,d,e = bounds
                tx,ty=tinjig.CONTROLLER_TRAVEL
                fit = "Exceeds controller travel." if d-a>tx or e-b>ty else "Check available travel and cord slack from your physical zero."
                self.carton_summary = (f"{count} assigned pocket(s) checked. Full travel from jig zero: X {a:.2f} to {d:.2f}, "
                                f"Y {b:.2f} to {e:.2f} mm. {fit}" +
                                (f" Lid diameter exceeds pocket spacing at {len(warnings)} pocket(s)." if warnings else ""))
                self.status.set(self.carton_summary)
            else:
                self.display()
            self.draw()
        threading.Thread(target=work, daemon=True).start()
        self.after(80, finish)

    def display(self):
        selected = self.layers.curselection()
        if self.carton_travel and self.map_mode.get() == "Travel":
            self.status.set(self.carton_summary)
        elif self.checked and selected:
            job,report,_ = self.checked[selected[0]]
            x0,y0,x1,y1=report["travel"]
            near=self.project.neighbouring_pockets(self.index, job.piece["w"])
            warning = (" This lid diameter overlaps pocket(s) "+", ".join(map(str,near))+" at the entered spacing." if near else "")
            self.status.set(f"{job.name} · {report['locations']:,} marked cells · {job.material.feed:g} mm/min · "
                            f"{job.material.pitch:g} mm rows. Travel including jig zero: X {min(0,x0):.2f} to {max(0,x1):.2f}, "
                            f"Y {min(0,y0):.2f} to {max(0,y1):.2f} mm. Check cord reach on the bed.{warning}")
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        w,h=max(c.winfo_width(),10),max(c.winfo_height(),10)
        layout = self.project.layout
        centers = [layout.centre(i) for i in range(len(layout.slots))]
        r = (layout.outside_diameter or min(layout.pitch_x, layout.pitch_y)) / 2
        x0,y0 = min(0,min(x for x,y in centers)-r), min(0,min(y for x,y in centers)-r)
        x1,y1 = max(0,max(x for x,y in centers)+r), max(0,max(y for x,y in centers)+r)
        selected=self.layers.curselection()
        job,report,provenance = self.checked[selected[0]] if self.checked and selected else (None,None,None)
        boxes = [job.geom.piece_rect,report["travel"]] if job else []
        if self.carton_travel:
            boxes.append(self.carton_travel)
        for box in boxes:
            x0,y0,x1,y1=min(x0,box[0]),min(y0,box[1]),max(x1,box[2]),max(y1,box[3])
        scale=max(.01,min((w-32)/(x1-x0 or 1),(h-32)/(y1-y0 or 1)))
        def xy(x,y):
            return (w/2+(x-(x0+x1)/2)*scale,h/2-(y-(y0+y1)/2)*scale)
        for i,(x,y) in enumerate(centers):
            tag=f"pocket{i}"
            color="#f8bb54" if i==self.index else "#8da1ad" if layout.slots[i].enabled else "#46515b"
            c.create_oval(*xy(x-r,y+r),*xy(x+r,y-r),outline=color,fill="#293945",width=2,tags=tag)
            c.create_text(*xy(x,y),text=str(i+1),fill=color,tags=tag)
            c.tag_bind(tag,"<Button-1>",lambda _,i=i:self.select(i))
        if self.carton_travel and self.map_mode.get() == "Travel":
            a,b,d,e=self.carton_travel
            c.create_rectangle(*xy(a,e),*xy(d,b),outline="#6fe0fb",dash=(4,2))
        elif job:
            mode = self.map_mode.get()
            if mode == "Burn map":
                g = job.geom
                bitmap=simulate.laser_input(job).resize((max(1,round(g.art_w*scale)),max(1,round(g.art_h*scale))))
                self.preview_image=ImageTk.PhotoImage(bitmap,master=self)
                c.create_image(*xy(g.x0,g.yt),image=self.preview_image,anchor="nw")
            elif mode == "Travel":
                a,b,d,e=report["travel"]
                c.create_rectangle(*xy(min(0,a),max(0,e)),*xy(max(0,d),min(0,b)),outline="#6fe0fb",dash=(4,2))
            else:
                partner=next((peer for peer,_,_ in self.checked if peer is not job),None)
                paths,message=outlines.circular_image_guide(job,provenance["image_perimeter_border_mm"],partner)
                for path in paths:
                    c.create_line(*(v for pt in path for v in xy(*pt)),fill="#6fe0fb",width=2)
                if not paths:
                    self.status.set(message)
        zx,zy=xy(0,0)
        c.create_line(zx-6,zy,zx+6,zy,fill="#ff8648")
        c.create_line(zx,zy-6,zx,zy+6,fill="#ff8648")
