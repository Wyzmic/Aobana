# Changelog

## 1.5: Filtered search, faster chosen-title search, CPU workers, manga page images

### Enhancements

- **Filtered search and pinned titles.** The **Filtered** switch next to **Exact** controls how title clicks work. It starts off: a click searches one title and scrolls to it. Turn it on to search several titles together. Titles you have chosen stay above a divider until you remove them with their × buttons, click the Aobana logo, or close the browser tab. **All** clears the current choice while keeping those pins.
- **Faster searches within chosen titles.** Aobana reads only the chosen books, subtitle shows, or manga series, then counts matches in the other titles in the background. On the measured large test libraries, a chosen-title search that previously scanned the whole library for minutes returned in under a second. A choice with no matching lines says so immediately.
- **CPU workers for search and indexing.** Separate Settings cards control each worker count. Automatic uses half the usable CPU threads. Long searches can start extra workers after a configurable delay (10 seconds by default, or zero to start them immediately); the remaining search and other-title counting then run across those workers.
- **Manga page images.** A manga result's page number in Search, Favorites, or the Media reader opens its image in a reusable browser tab when the image is available beside the `.mokuro` file.
- **Media and search navigation.** Media sits next to Search in the top bar. Its titles can be sorted by name, episode/chapter/volume count, or line count in either direction. The Media list and search sidebar load 500 titles at a time, and the search options wrap one by one on narrow windows.
- **Moving databases and reading large reports.** Moving the database folder in Settings includes its companion files and shows bytes and time remaining. Check library draws long reports as you scroll and keeps selections across the full report.
- **Long-task notices.** Another Aobana tab wakes when indexing or a library check starts, and notices can be dismissed across tabs. Future manga re-index notices include manga as well.

### Bug Fixes

- Leaving a search tab or starting a new search cancels the old server search, so it does not keep using CPU in the background.
- A chosen title with no results, or one outside the selected media category, no longer starts a whole-library search. Opening a very large library no longer briefly says **Your library is empty** while its first title list is loading.
- **Manga only** indexing starts without a subtitle/book estimate; Check library is disabled for that scope, and the completed run lists manga in its summary.
- An EPUB with an unreadable chapter is listed as failed with the file and reason, and Check library reports it. Older books indexed with no chapters are checked once on the next index run.
- Open folder in Library and Settings now reports a failure instead of appearing to do nothing. On Windows, it opens Explorer directly and brings the folder window above the browser.
- Search worker guidance no longer claims a fixed slowdown above 16 workers; the benefit and memory use depend on the machine and query.
- A direct Termux update from 1.0–1.3 moves the earlier settings and database layout into `data/` and `data/db/` while keeping media files and custom folder choices.

## 1.4: Manga, `.ass` furigana, Settings, in-app setup

### Enhancements

- **Manga.** Aobana searches `.mokuro` OCR text as a third media type, with a folder per series, its own switch, database (`manga.db`), and Media list. Results include page numbers. Aobana uses the text saved by mokuro and puts pages of a spread in reading order.
- **`.ass` furigana.** Small furigana lines are placed over their kanji. The first index run after updating re-reads `.ass` and `.ssa` files; `.srt` files and books stay as they are.
- **Settings tab.** Media, folders, databases, search cache, favorites, port, and reset controls moved out of Library. Each media can be hidden while its index is kept, or its database deleted after a confirmation.
- **Setup in the app.** New installs choose media and folders at first start. Updates from 1.3 or earlier show that setup once with existing folder choices filled in. Reset all settings to default brings it back.
- **Furigana lookups in the index.** An older index builds its lookup table once through Update or an index run. On a measured 122 GB library, this avoided a roughly 20-minute delay when opening a book.
- **Check library.** Files directly in a media folder take priority over copies in subfolders. Duplicate lists have **Invert selection**, and the estimate remains until files change.

### Bug Fixes

- Windows setup can update a running Aobana and can update a per-user install when launched as administrator. Uninstall leaves optional data removal unticked.
- Searching a media type that is off or has no database no longer returns results from another type.
- The sidebar lists all titles again when the chosen titles have no match.

## 1.3: Faster large-library search and search inside a title

### Enhancements

- **Faster searches.** A one-time index table stores displayed line lengths, about 10 bytes per line. Together with the search changes, common-word searches took about 45% less time in the measured library.
- **Optional search cache.** Searches that take a while can be kept on disk, up to 1 GB, to appear at once after a restart. The cache starts off and can be cleared without removing the index.
- **Search inside a title.** An open show or book in Media has a search bar for episode/chapter names and sentence text, with results grouped in reading order.
- **Several titles at once.** Sidebar clicks add or remove titles from the search filter; **All** clears the choice.
- Library shows saved folder counts immediately and updates them in the background. Long indexing and library checks show a notice on every tab. The Guide shows the version and a Changelog button.
- Databases and their companion files moved into `db` inside Aobana's data folder at first start. A custom database folder stayed where it was. Large book libraries gained a chapter table built by the next index run.
- Check library counts steadily and Stop responds promptly; chapters named only by file number show their place in the book.

### Bug Fixes

- Very long EPUB paragraphs no longer break the results page.
- Opening the context around a book line no longer hangs on a large library.

## 1.2: Automatic updates, folder pickers, and settings across ports

### Enhancements

- **Update automatically.** The update window can download, verify, install, and restart Aobana on Windows, macOS, and Linux. Android uses **Update now**. An unsuccessful desktop install starts the old version again.
- The first start after an update shows the release's notable changes.
- **Change folder** opens the system folder dialog on Windows, macOS, and Linux. The text field remains available, including on Android.
- Changing the port keeps browser settings, language, theme, and favorites. **Reset all settings to default** keeps the library and its index.
- The top bar stays visible on every tab. Japanese and English wording was revised, and icon-only controls gained screen-reader labels.

### Bug Fixes

- A search for a lone auxiliary such as `は` finds that form rather than unrelated forms.
- The Windows welcome and what's-new windows keep a consistent text size, and their icon can no longer be dragged away.

## 1.1: macOS, Linux, `.ass` subtitles, and Check library

### Enhancements

- Added an Apple Silicon `.dmg`, a Linux tarball installer, and an AppImage. macOS uses port 5005 because AirPlay Receiver can use 5000.
- `.ass` and `.ssa` Japanese dialogue can be indexed, including bilingual subtitle files; signs, drawings, and other-language lines are left out.
- **Check library** finds non-Japanese subtitles, alternate episode rips, SubPlz output sets, and duplicate books. Ticked files are excluded from the index without being deleted and can be put back.
- Indexing can use several processes, run one media type at a time, estimate size and duration, and warn before adding more than 10 GB. Unreadable files are reported while the rest continue.
- Indexing and Check library can be stopped after a confirmation; completed work is kept so the next run resumes.
- Subtitle titles lose release tags and recognize more episode number formats. Book titles keep volume numbers; chapters follow reading order, including numbered headings in one-chapter books.
- Media and search sidebars load in pages, long searches show time remaining, and short-word furigana is centered.
- Default folders became `Subtitles` and `Books`; a 1.0 update renamed the original defaults once. Android installation creates those folders. Android's update window can skip a version.

### Bug Fixes

- Invisible direction marks and written-out HTML codes are removed from subtitle text.
- Random sorting keeps its order across tab changes, and a cancelled search stops promptly.
- The 1.0 index can be re-read from Library without losing Favorites.

## 1.0: First public release

### Enhancements

- Offline search over your own Japanese `.srt` subtitles and `.epub` books, including conjugations, kana readings, exact matches, and excluded words.
- Furigana on sentences, using book ruby when available, with a one-click visibility switch.
- Context around results and full episodes and chapters in Media.
- Favorites, recommended/chronological/length/random sorting, and media and title filters.
- Japanese and English interface, four themes, keyboard shortcuts, and a phone-sized layout.
- An English/Japanese Windows installer including Python and required packages, with per-user or all-user installation.
- Android installation through Termux and a release check at startup.
