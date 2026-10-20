# Third-party notices

露草 / Aobana is licensed under the GNU General Public License v3.0 (`LICENSE`). The Windows
installer and the macOS and Linux downloads also ship the software below, each under its own
license. The full license text of every package is installed with it: `python\LICENSE.txt` for
Python on Windows, `python/lib/python3.14/LICENSE.txt` on macOS and Linux, and each package's
`<package>.dist-info` folder under `site-packages` for the rest.

| Component | Version | License | Copyright |
|---|---|---|---|
| Python (embeddable package) | 3.14.8 | PSF License 2.0 | © 2001 Python Software Foundation; includes OpenSSL, libffi, SQLite, zlib and others, listed in `python\LICENSE.txt` |
| Python (python-build-standalone, macOS and Linux) | 3.14.8 | PSF License 2.0 | © 2001 Python Software Foundation; built by Astral's python-build-standalone (BSD-3-Clause); includes OpenSSL, libffi, SQLite, zlib and others |
| SudachiPy | 0.6.11 | Apache License 2.0 | © Works Applications Co., Ltd. |
| SudachiDict-core | 20260723 | Apache License 2.0 | © Works Applications Co., Ltd. |
| Flask | 3.1.3 | BSD-3-Clause | © 2010 Pallets |
| Werkzeug | 3.1.8 | BSD-3-Clause | © 2007 Pallets |
| Jinja2 | 3.1.6 | BSD-3-Clause | © 2007 Pallets |
| MarkupSafe | 3.0.3 | BSD-3-Clause | © 2010 Pallets |
| itsdangerous | 2.2.0 | BSD-3-Clause | © 2011 Pallets |
| click | 8.5.0 | BSD-3-Clause | © 2014 Pallets |
| blinker | 1.9.0 | MIT | © 2010 Jason Kirtland |
| Beautiful Soup | 4.15.0 | MIT | © Leonard Richardson |
| soupsieve | 2.9.2 | MIT | © 2018–2026 Isaac Muse |
| typing_extensions | 4.16.0 | PSF License 2.0 | © Python Software Foundation |
| Noto Sans JP | — | SIL Open Font License 1.1 | © 2014–2021 Adobe; `static/fonts/OFL.txt` |

The source repository includes only Noto Sans JP from this list (`static/fonts/`, with its
`OFL.txt`); `requirements.txt` names the Python packages, which pip installs from PyPI.

## Acknowledgements

- **[Nadeshiko](https://github.com/BrigadaSOS/Nadeshiko)** (AGPL-3.0) inspired several of the
  search page's features. No code was copied from it.
- **[mokuro](https://github.com/kha-white/mokuro)** (GPL-3.0) writes the `.mokuro` files that Aobana
  reads for manga. Aobana reads only those files; no mokuro code is included.
