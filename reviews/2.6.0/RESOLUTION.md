# Resolution of the 2.6.0 follow-up review

Each finding is fixed in its own release, in the order the review recommends.
All seven are fixed in 2.6.1-2.6.3, merged to `main`; none has been published yet.

| ID | Resolution | Release |
| --- | --- | --- |
| F1 | The loaded atlas folder stands for the loaded atlas only while its files match the load-time signature; once they changed or went missing, every replacement is refused (restore them, or save and reopen, which checks by checksum). | 2.6.1 |
| F2 | Stored sections without a recorded registration give "not verified", never current, in Results, the step list and exports, until the section is opened once. Sections no longer in the project stay as mapped. | 2.6.1 |
| F3 | Checkerboard and blink on a separate presentation item; saved and exported pixels stay canonical; leaving the step ends the comparison. | 2.6.2 |
| F4 | The repaired object stays selected (by its id) through every repair step and section switch. | 2.6.2 |
| F5 | Repair remaps each changed section once, in order (naming the next and the number left), then builds once; a missing origin no longer hides a changed section. | 2.6.2 |
| F6 | The Mark review complete command shares the checklist gate. | 2.6.2 |
| F7 | A TIFF stack is decoded once for all its page sections, which share it read-only; progress and Stop between sections. Benchmark (60 × 2048², 480 MiB): 60 → 1 decodes, 11.4 → 5.0 s, traced peak 1.8 → 0.95 GiB (`tests/benchmark_tiff_pages.py`, `release_validation.md`). | 2.6.3 |

The review's probes (`evidence/probe_followup.py`) after 2.6.1: the atlas
case refuses the reload (and export refuses the changed files); the legacy
case reports "not verified" before the section is visited and "registration
changed" after. After 2.6.2: the checker case saves the original preview (0
changed values) and reopens it; the review case refuses the command
("Tick each point of the checklist first."); the repair case keeps
`merged cells` selected and ends current; the multi-repair case moves on to the
second section.

The broader gates (representative real data, clean native installs, observed
user sessions) remain recorded as pending in `release_validation.md`.
