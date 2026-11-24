# Open Studio files from Windows

Drop one JPG, PNG, HEIC or other supported picture onto the Studio window or its
normal desktop shortcut. For a saved job, open its folder's `job.json` from
**1 Picture → Open saved Studio picture job**, or use an editable `.lpsjob`.
Studio checks the saved source and commands before loading it. A new window
starts disconnected. An active run or machine operation blocks replacing the
picture or job.

To create a portable editable job, check the job in step 4 and choose
**Save editable Studio package**. It includes the source image, settings and
checked passes. Keep it private if those files contain personal artwork or
paths. It excludes run photos, position records, logs and live machine state.
Opening the package verifies a copy in Studio's local **Imported Jobs** folder.
The existing job-folder format continues to work.

The optional `register-open-with.ps1` lists Studio in the current Windows
account's **Open with** menu. Pass the normal Studio shortcut's Pythonw path
using `-Pythonw`. The command prints a preview by default. Choose `-Apply` when
you want to register the menu entry. It does not select a default app.
