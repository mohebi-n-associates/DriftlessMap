# Resolution of the 2.6.0 follow-up review

Each finding is fixed in its own release, in the order the review recommends.
Releases are merged to `main`; none has been published yet.

| ID | Resolution | Release |
| --- | --- | --- |
| F1 | The loaded atlas folder stands for the loaded atlas only while its files match the load-time signature; once they changed or went missing, every replacement is refused (restore them, or save and reopen, which checks by checksum). | 2.6.1 |
| F2 | Stored sections without a recorded registration give "not verified", never current, in Results, the step list and exports, until the section is opened once. Sections no longer in the project stay as mapped. | 2.6.1 |
| F3 | Checkerboard and blink on a separate presentation item; saved and exported pixels stay canonical. | 2.6.2 (planned) |
| F4 | The built object stays selected through a repair. | 2.6.2 (planned) |
| F5 | Repair remaps each changed section in turn, then builds once. | 2.6.2 (planned) |
| F6 | The Mark review complete command shares the checklist gate. | 2.6.2 (planned) |
| F7 | A TIFF stack is read once when its pages become sections, with a page-read count and a large-stack benchmark. | 2.6.3 (planned) |

The review's probes (`evidence/probe_followup.py`) after 2.6.1: the atlas
case refuses the reload (and export refuses the changed files); the legacy
case reports "not verified" before the section is visited and "registration
changed" after.

The broader gates (representative real data, clean native installs, observed
user sessions) remain recorded as pending in `release_validation.md`.
