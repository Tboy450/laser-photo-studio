import sys,unittest,tempfile,tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
from lps import ports,jobs,machine
from lps.app import App

class PortChoices(unittest.TestCase):
    def test_saved_sockets_survive_unplug_and_replug(self):
        settings=dict(port='COM4',known_ports=['COM4','COM6'])
        for detected in [[],[('COM4','CH340')],[('COM6','CH340')]]:
            self.assertEqual(ports.choices(settings,detected,'COM4'),['COM4','COM6'])
        self.assertEqual(ports.choices(settings,[('COM10','USB')],'COM6'),['COM4','COM6','COM10'])
    def test_access_denied_not_claimed_to_prove_another_sender(self):
        import serial
        with patch.object(serial.Serial,'open',side_effect=PermissionError('Access is denied')):
            with self.assertRaises(machine.LinkError) as caught:machine.SerialWire('COM4').open()
        self.assertIn('restricted permissions',str(caught.exception))
        self.assertIn('may hold',str(caught.exception))
    def test_refresh_changes_choices_not_selection_or_machine(self):
        with tempfile.TemporaryDirectory() as folder:
            root=tk.Tk();root.withdraw()
            with patch.object(jobs,'SETTINGS_FILE',Path(folder)/'settings.json'),patch.object(jobs,'LOCK_FILE',Path(folder)/'sender.lock'),patch.object(machine,'list_ports',return_value=[('COM6','USB-SERIAL CH340')]),patch.object(machine.SerialWire,'open',side_effect=AssertionError('No hardware in test')):
                jobs.save_settings(dict(port='COM4',baud=115200,known_ports=['COM4','COM6']))
                app=App(root,SimpleNamespace(demo=False,picture=None,perimeter=None))
                try:
                    before=(app.port_var.get(),app.origin_set,app.mat.key,app.piece.copy())
                    app.refresh_ports()
                    self.assertEqual(tuple(app.port_box['values']),('COM4','COM6'))
                    self.assertEqual((app.port_var.get(),app.origin_set,app.mat.key,app.piece),before)
                    self.assertIsNone(app.worker)
                    self.assertIn('COM4: saved choice, not detected now',app.port_desc['text'])
                    self.assertIn('COM6: USB-SERIAL CH340',app.port_desc['text'])
                    app.port_var.set('COM6');app.refresh_ports()
                    self.assertEqual(app.port_var.get(),'COM6')
                    self.assertEqual(tuple(app.port_box['values']),('COM4','COM6'))
                    self.assertEqual(app.settings['port'],'COM4') # only Connect saves the chosen default
                    def labels(w):
                        return [str(c.cget('text')) for c in w.winfo_children() if 'text' in c.keys()]+sum([labels(c) for c in w.winfo_children()],[])
                    self.assertIn('(these are for your different USB ports)',labels(root))
                finally:
                    for task in root.tk.call('after','info'):root.after_cancel(task)
                    root.destroy()
if __name__=='__main__':unittest.main()
