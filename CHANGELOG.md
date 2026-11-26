# Changelog

## 3.1: Quit from the page, Yomitan on a phone, and minimized console

### Enhancements

- **Quit from the page.** The **✕** at the right of the top bar quits Aobana. **Quit Aobana** stops it and shows that it has quit; the next start opens **Search**. **Quit and keep tabs** leaves every tab on its page, and the next start uses them again instead of opening a new tab.
- **Yomitan on a phone.** A tap on a menu, a sheet, a title, a row, a link in a book or the Guide's contents no longer starts a lookup, and a long press no longer opens the browser's link menu. With a mouse, titles and rows are still looked up.
- **The console window starts minimized.** The window Aobana runs in (the Terminal on macOS and Linux) starts minimized and comes back by itself if Aobana fails to start. **Console window** in the **Settings** tab shows it again.

**The app**

- Starting Aobana while one of its tabs is still open uses that tab instead of opening another, also after the console window or Terminal was closed. When Aobana comes back on a new build, such as after an update, a kept tab reloads in place and reopens Reading mode at the same page.
- A tab that loads while Aobana is not running says so (**Aobana is not running**) and loads the page by itself once Aobana runs, instead of the browser's error page.
- The browser's **Back**, and a phone's back gesture, close what is open first, the topmost first: a window, a menu, the title sheet of **Search**, the Guide's contents, Reading mode's panels, then Reading mode itself. Only then does it leave the page.
- The filter chip of **Search** can no longer be selected, like a row in **Media**.
- The top bar's tabs have a name for screen readers when only their icon shows.

**Reading mode**

- **Scroll to turn page** (**Swipe to turn page** on a touch screen): when it is off, the mouse wheel, a trackpad and a swipe turn no page in page view; the keys and the page edges still do. It is in Reading mode's display panel and the **Settings** tab, for books, subtitles, manga and Custom, and on by default.
- On a phone, a tap on a page edge turns the page (**Tap edges to turn page**, **Tap zone width**). One of the two switches always stays on: turning off the last one turns the other back on. While text is selected, an edge tap only clears the selection, and the next one turns the page. Moving **Tap zone width** tints both edges.
- The display panel shows the two page-turn switches only where they work: in page view, and for manga in single pages.
- **Content width** and **Content height** are a share of the screen, from 10% to 100%, so the text area stays the same when the font size changes. A window smaller than the text area makes it smaller, down to a thin margin. Scroll view has a size of its own, **Content size (scroll)** in the **Settings** tab. While one of them moves, the margins around the text are tinted. A width or height set in 3.0 goes back to the new defaults: 75% wide, 85% high, 75% in scroll view.
- **Font size** goes from 8 px to 72 px, and **Subtitle timestamps** are on by default. In the display panel, **Subtitle timestamps** is hidden when subtitles are shown from the index (which does not store times).
- **Click zone width** (**Tap zone width** on a touch screen) is 25% by default and goes up to 40%. In page view a zone stops at the edge of the text or the manga page, so it never covers them, and at least a 30 px strip stays free on each side so an edge can always be clicked or tapped without touching the text.
- Notes are copied as plain text by default, with quotes in 「」 (Japanese) or `"..."` (English). A **Copy as Markdown** switch sits beside **Include furigana** in the Notes panel, the **Saved** tab, and **Settings** (shared by every medium).
- Manga shown as text, when its page images are missing or it is read from the index, scrolls in vertical writing, the cards running right to left, and looks more compact. **Writing direction** in the display panel switches it to horizontal writing.
- Custom's .txt and .md files open from the file, and a .md keeps its formatting: bold, italic, strikethrough, highlights, inline code, lists, quotes and code blocks. When the file is missing, the indexed text is shown, with a notice, as for subtitles, books and manga.
- Links in a Custom .md work in Reading mode. A link to a subpage, such as an album's songs exported from Notion, or to another page of the library opens that page, and **Back** returns to the link. A web address opens in a new tab. On a phone, a tap on a link does not start Yomitan.
- **Missing file notice** in the **Settings** tab turns off the notice that Reading mode is showing the indexed text because the original file is missing. It is on by default.
- Going back to a chapter or volume with the arrow keys or the top bar's previous and next buttons opens it where you left it, until Reading mode closes. A chapter not yet opened, **Contents** and the buttons at a chapter's end open at the start.

### Bug Fixes

- On a phone, tapping an open menu or sheet, such as the theme and accent menus in **Settings**, the sort menus, the i+1 menu or the title sheet, made Yomitan look up the page text under it. A tap outside an open menu closed it, started Yomitan and also opened what was under the finger. A tap on a menu now only does what the menu does, and a tap outside it only closes it. With Yomitan's scan key on a computer, the text under an open menu is no longer looked up either.
- On a phone, tapping a title in **Search**, a row in **Media** or the filter chip made Yomitan look up its name, and so did tapping the folder path of **Media**, Reading mode's font list, bookmark names and note places, the Anki deck names, the columns when importing known words, the ✕ of recent searches and filter chips, and the Guide's contents. A tap on them no longer starts a lookup. With a mouse, titles and rows are still looked up.
- On a phone, choosing a section in the Guide's contents made Yomitan look up the text that scrolled under the finger. It no longer does.
- On a phone, jumping to the last sections in the **Guide**'s contents could leave them partly hidden behind the browser's bar. The last section now scrolls to the top of the screen.
- On a phone, tapping a link inside a book, such as the contents or a footnote, started Yomitan. It now goes to the link without a lookup.
- A long press on a title in **Search**, a section of the Guide's contents, or a link inside a book on a touch screen opened the browser's link menu for an address that leads nowhere. It no longer does.
- In Reading mode's page view, changing a setting such as the font size, line height or width could show the text after the page you were reading and put its first lines on the page before. The page you are reading now stays, and a setting changed back shows the same page again.
- In Reading mode's page view, moving a slider such as the width or height could show the start of the next sentence at the end of the page, and leave it there after letting go. The page now ends at a whole sentence while the slider moves.
- Switching a manga from single pages to the scroll strip could move to the next page. It now keeps the page you were on, and the page counter follows the strip as you scroll.
- In Reading mode opened from **Search**, **Back** after following a link reloaded the page and closed Reading mode. It now returns to the link.
- Opening Reading mode on a fresh page load (such as jumping to a bookmark or note from **Saved**, or reloading a kept tab) could land one page early in page view. It now opens on the target page.
- On a phone, the shortcut opened a second Aobana tab, or showed Firefox's last tab, whatever it was. It now opens the Aobana tab last on screen, at the page you left; Chrome reuses the tab it opened for Aobana.
- On a phone, Ctrl-C in Termux, or closing its session, left Aobana running with no session to stop it. It now quits Aobana.
- The phone installer asked to allow Termux *Display over other apps*, which Termux from Google Play does not offer. It now says how to quit Aobana.

## 3.0: Titles in more than one media, and three more accent colors

### Enhancements

- **Titles in more than one media.** A title found in two media, such as an anime and its manga with the same name, is one entry per media in the title list of **Search**, each with its media's badge, and its counts and filter keep them apart.
- **Three more accent colors.** **Settings** has Cyan, Indigo and Gold, eleven accent colors in all.
- Shutting a fold near the end of a page keeps it where it was, instead of moving the page down.
- In the **Haze** theme with an accent color, the sidebar, cards and text boxes take the accent's tint too, not only the page behind them.
- In the **Paper** theme, the ending of a highlighted word in the results (such as the た of 食べた) is darker and easier to read.

### Bug Fixes

- The subtitles badge (**SUBS**, **字幕**) changed color with the accent color. It is now the same blue with every accent color, in **Search** and **Media**.
- Clicking or tapping a fold's or an episode's header several times quickly selected the text below it. It no longer does.
- On a Mac, scrolling past the top of **Search** or **Media** could open a gap under the top bar where the results showed through. The bars now move together.
- Double-clicking a title in the title list of **Search** picked it and dropped it again. It is now picked once.
- On a phone, a thin line of the list showed between the top bar of **Media** and the folder path under it. It no longer does.
- A Custom library indexed on Windows and opened on macOS, Linux or Android showed its `.md` folders empty. They now open.

## 2.9: A faster Easiest and Hardest, and keyboard use

### Enhancements

- **A faster Easiest and Hardest.** The count behind the two Media sorts runs on the index workers set in **Settings**, about 5× faster on a large library, and its figures are kept after a restart. Its notice stays at the bottom right on every tab until closed.
- **Keyboard use.** The dropdowns work with ↓ ↑ Home End, Enter and Escape, and an open window keeps the keyboard until it closes. **Enter** opens the sentence card picked with **D** and **A** in **Media**.

**Reading mode**

- The footer's count, % and bar count the text up to the end of the screen, so a part's last page or screen shows 100%. The saved place and a bookmark's % stay the first character on screen; a manga volume shows 100% on its last page.
- **Contents** shows a file's folders as a tree that opens and shuts, with a filter from 20 items.
- Deleting a note asks once, as in **Saved**. In both, the second **Delete** appears where the first one was, with **Cancel** before it, so notes can be deleted one after another by pressing one place.

**The app**

- **Index library** and **Check library** are grayed while the Easiest and Hardest count runs, and the count waits for an index run or a check to end.
- The notices stack in one column at the bottom right, the newest lowest, with **Saved**'s **Undo** in the same column.
- The tab strips of **Settings** and **Saved** scroll a tapped tab fully into view and take ← → Home End.
- ↓ and ↑ scroll the page when there are no sentence cards, and Escape closes the phone's title sheet.
- Screen readers hear the windows as dialogs, and the search, filter and port fields have names.
- When the server cannot be reached, bookmarks, notes and Reading mode settings, the changes in **Settings** and a search say so, instead of looking saved or leaving the old results.

### Bug Fixes

- Two tabs open on one work could undo each other's bookmarks. Adding or deleting a bookmark, there or in **Saved**, now changes only that bookmark.
- A media folder the app was not allowed to read showed 0 files. The Library and **Settings** now say it cannot be read, and so for folders inside it.
- A media folder renamed or deleted while Aobana ran kept its files in the Library's figures. It is now counted again.
- A `.json` file that is not a word list from Aobana Reibun, such as a reading-data or favorites backup, was read as known words. It is now refused.
- A favorites file from a newer version was accepted, and one too big for the browser's storage showed as imported but was gone after a reload. Both now get the "could not be read" note, and the list stays as it was.
- A `config.json` that could not be read was overwritten with the defaults at the next save. It is now kept as `config.json.bad`.
- With **Match device**, Chrome on Android could show another accent color until the page was touched. It now reads the device's accent again after the page opens.
- On a phone, the app's icon appeared in the gallery. It no longer does.

## 2.8: Bookmarks, Easiest and Hardest, and Settings → Data

### Enhancements

- **Bookmarks.** A work in Reading mode holds up to 100 bookmarks. **B** adds one at the current place, or removes the one there. The bookmark button lists them, newest first; **Contents** has a **Bookmarks** tab beside the contents, and **Saved → Continue reading** lists each work's bookmarks. A 2.7 bookmark becomes the first of the list.
- **Easiest and Hardest.** With known words imported, the Media list sorts by **Easiest** or **Hardest**, and each work shows the share of its words known and of its sentences with no unknown word (i+0) and with one (i+1).
- **Settings → Data.** A **Data** tab holds the known words, the favorites' export and import, and an export and import of reading data (places, bookmarks and notes in one file).

**Reading mode**

- Outside manga a bookmark's place is its chapter and line, so a font or size change keeps it.
- Importing reading data shows what is new, newer here, newer in the file and the same, for works, bookmarks and notes, and offers **Keep newer**, **Merge** (bookmarks from both) or **Replace**. Each import first backs up the reading data in the data folder, keeping the newest 5.
- Importing favorites shows how many are new and offers **Add to these** or **Replace**.
- The browser's Back returns to the place before a jump from **Contents**, a bookmark or a note.
- In vertical text and in manga, the top bar's **Next** is on the left with a left arrow and **Previous** on the right.
- A manga bubble of several OCR lines is one sentence for Yomitan; copying inside one bubble gives one line.
- Screen readers hear the page count on a page turn and the part's title on a part change, and no longer read furigana shown only on hover.

**Known words and i+1**

- The Anki import has **Leave out suspended cards**: a note counts only if one of its cards is not suspended (Aobana Reibun 1.9 or later).
- The Easiest and Hardest count runs in the background, once, then only for the files an index run changed (about 17 s for 4.3 million lines on a Mac), with a progress notice on a large library.

### Bug Fixes

- A link in a book, such as a note number, could open the page before its target. It now opens the target's page.
- A manga page in Reading mode could show an OCR box twice. It now shows one, by the rule the search index already used.
- Speaker and sound tags in subtitles, such as `（拍手）`, counted as unknown words for i+1 and **Recommended**. They no longer count; a line that is only `（…）` still does.
- Words with rare kanji (CJK Extensions B to J) did not count as words for i+1, **Recommended** and the Media sorts. They now do.
- Kanji of CJK Extension J were not read as kanji in ruby, the reading search and a book's kanji checks. They now are.

## 2.7: Reading notes, the Saved tab, and Appearance

### Enhancements

- **Notes in Reading mode.** **Notes** (or `N`) writes a note or a question at your place in the work, with the selected text as its quote when you select some first. Notes can be jumped to, edited, deleted and listed for the part or the whole work. Copy buttons copy the notes as Markdown with or without quotes, the part's full text, or the current page or area, with or without furigana.
- **Saved tab.** **Favorites** became **Saved**, with **Favorites** (saved sentences, as before), **Continue reading** (every work opened in Reading mode, latest first, with its place and bookmark, filtered by media; ✕ removes a work and **Undo** brings it back) and **Reading notes** (every work's notes, to jump to, copy, edit or delete).
- **Appearance.** **Settings → General → Appearance** sets the theme mode (**Match device**, **Light**, **Dark**), the light and dark theme, an accent color (**Default (blue)**, teal, green, purple, pink, red, orange, gray, or **Match device**) and the language. The accent colors buttons, links, the active tab, search hits and the app icon. The language and theme menus moved out of the top bar.

**Reading mode**

- Custom folders of `.txt` and `.md` files, and those files, have a **Reading mode** button: pages or scrolling, vertical or horizontal text, furigana, bookmarks and notes, as for books.
- One **Layout** setting (**Paginated** or **Scroll**), separate from the writing direction; subtitles default to **Scroll**, other media to **Paginated**. 2.6's settings carry over.
- New settings: **Content height**, **Image size** (books and manga strips), **Hide top bar (hover top)** and **Hide top bar on scroll**.
- The reading position is kept to the character across setting changes, window resizes, layout and direction switches, **Continue reading**, bookmarks, notes and links, and to the line in scrolling layouts, also when pictures load late.
- **Click zone width** and **Click edges to turn page** no longer change which text is on the page.
- A book's blank line is drawn as one blank line in both directions.
- A bookmark or note whose part no longer exists after re-indexing opens at the last place read, with a notice.
- The keyboard shortcuts window has **App** and **Reading mode** tabs and opens on the Reading mode keys while reading; the Guide has a button for it, on phones too.

**Media and Custom**

- **Recently read** sorts the Media list and a Custom folder's subfolders by when each work was last read in Reading mode, with an **Unread** line above the first work not read yet.

**Settings**

- **Settings** has **General**, **Reading mode** and **Advanced** subtabs, and Reading mode's settings show one media at a time.

**Updates**

- Updating from inside Aobana works from 2.2 or newer. The code that only moved settings from before 2.0 and removed files installed by 1.0–1.6 is removed; on an older version, install 2.7 from the release page.

### Bug Fixes

- Books that set their own line height ignored **Line height**. It now applies to every book.
- Vertical text had no gap between paragraphs. It now matches horizontal text.
- Reading mode's font list could include Chinese and Korean fonts. It now lists Japanese fonts only.

## 2.6: Reading mode

### Enhancements

- **Reading mode.** Press **Reading mode** on a show, book or manga page in **Media** (or the reader icon on any episode, chapter or volume) to read from the original file (`.srt`, `.ass`, `.ssa`, `.epub`, `.mokuro`). Books and subtitles offer vertical or horizontal text, paginated or scrolling layouts, furigana controls, themes and bookmarks; manga shows the page images with the OCR text on top, one page at a time or as a vertical strip. Aobana remembers your place per work, and falls back to the indexed text with a notice if the original file cannot be read.

**Reading mode**

- **Settings** has a **Reading mode** card with separate defaults for subtitles, books and manga, shown only for media that are turned on: theme (including **Sepia**), writing direction and default layout for vertical and horizontal text, furigana (**Show**, **Hover / tap**, **Hide**), font (**Default (Noto Sans JP)**, **Serif (device)**, or any Japanese font installed on your device), weight, size, line height, content width, progress bar, edge-click page turning, subtitle timestamps, and manga layout and text boxes. **More in Settings** inside Reading mode opens that media's section, and **Restore defaults** resets the open media's display settings.
- A book's chapter is found in the `.epub` by its text, so it starts at its own heading (also a heading on a page of its own) and ends where the next chapter begins, even when the book quotes the chapter's lines elsewhere.
- Links inside an `.epub` book (contents, notes and back links) open their target, including across chapters. The browser's Back button returns to the place before the link, Forward redoes the jump, and Back from the opening place closes Reading mode.
- A **Contents** drawer lists the work's episodes, chapters or volumes, and a bookmark can be set, jumped to, moved or cleared per work. Skipping quickly through parts cancels earlier loads and opens only the last one.
- A manga volume with no page images shows each page's text on a card using the manga text settings, with furigana that the OCR fused into the line shown as ruby. Double-clicking or double-tapping a zoomed manga page resets the zoom.
- Keyboard shortcuts work throughout Reading mode: arrow keys and `A`/`D` turn pages or scroll (holding a key in a scrolling layout scrolls steadily until released, and `↑`/`↓` or `←`/`→` step between parts depending on the layout), `[` / `]` switch parts, `T` opens **Contents**, `B` opens bookmarks, `F` cycles furigana, `S` opens **Display**, `0` resets manga zoom and `Esc` closes open panels or Reading mode.

**Media and Custom**

- Custom is faster on large libraries: Markdown titles are cached instead of scanned per result, a folder's **Content** search reads only that folder's lines, and single-file folders are found in one pass.

**Library and indexing**

- An **Index library** run where nothing changed finishes sooner: each file is checked once, no extra indexing processes start, and Custom skips re-reading Markdown pages and clean-up passes. Indexing also skips the ruby pass on subtitle and manga lines that contain no `(`, and finds each book sentence's furigana once instead of twice.
- **Check library** cleans each subtitle line once instead of twice and reads the file list once.
- A book page that only shows a part's title, above the chapters of that part, is no longer indexed as a chapter of its own. This applies to newly indexed books; books already in the index keep their chapters until they are read again.

### Bug Fixes

- A damaged pending book filter file (for example after an interrupted run) stopped every later book index run until it was deleted by hand. Aobana now sets the damaged file aside and logs it so indexing can continue.
- A `.mokuro` file saved with a UTF-8 byte order mark (BOM) could not be read. It is now read normally.
- With Custom on, the time left shown under **Preparing the names inside the works...** in **Media** did not count Custom's files.

## 2.5: See what a title search found

### Enhancements

- **See what a title search found.** Every title search shows the matching part of each name in bold: the Media list, a work's episodes and chapters, the Search sidebar's titles, and Custom's folders, files and headings.
- **Folders first in Custom.** A Custom page's **Titles** filter lists the folders whose name matches first, then the files whose own name matches, under **Inside the folders**.

**Media and Custom**

- The names inside the works are saved beside the databases, so after the first start the Media list's **Titles** filter finds them in seconds: 3.1 s on a library of 127,978 subtitle files and 590,495 chapters, where 2.4 took 36.7 s at every start.

### Bug Fixes

- On a large library, the Media list's **Titles** filter could take half a minute or more to answer, and longer while a word was typed with a Japanese input method. It now answers at once with the works and shows **Preparing the names inside the works...** with the time left, then adds the names inside the works when they are ready.
- A book's chapters matched the Media list's **Titles** filter by the book's author, so a filter for an author listed every chapter of their books under **Inside the works**. A chapter now matches by its own name; the books still match by author.
- A book's chapter in search results could show without its author until Aobana was restarted.
- On a Mac, a folder spelled in another case than one already chosen (`SUBS` beside `subs`) was accepted in the **Settings** tab as a second folder. It is now refused, as on Windows.
- Werkzeug, the library Aobana's server runs on, is updated to 3.1.9, which fixes how it checks file paths on Windows.

## 2.4: Search the lines in the Media list

### Enhancements

- **Search the lines in the Media list.** The Media list now has **Titles** and **Content**, as a work's page does. **Content** searches the lines of every work on the tab, with **Exact** and **Ruby only**, and a hit opens its work at that line.
- **Find names inside the works.** The Media list's **Titles** filter also finds the episodes, chapters, volumes, and Custom folders and files whose names match, listed under **Inside the works** after the works. An episode, chapter or volume opens its work with that file open.

**Media and Custom**

- A show's page has a **Specials** group, after **OVA** and before **Movies**, for files marked as specials (`SP`, `S00E01`, スペシャル, 特別編 and the like).
- A page's search in **Media** comes back only with the browser's Back, Forward or reload. A page opened by a click (the path, a row, a tab) opens at the top with an empty search box.
- A **Content** hit on a Custom folder page opens its file at that line.
- A Custom folder page loads its next 500 rows as you scroll, as the rest of **Media** does.

**The page**

- **Read more** in the window shown after an update opens the changelog in Aobana. The changelog's **View on GitHub** opens the release page.

### Bug Fixes

- On a show's page, an episode with a season mark (`S01E01`) went to **Movies** when its title or the show's name held a word for a film. It now stays in its season. 映画 before another kanji (映画館, 映画祭) is no longer read as a film, and `OAD`, `OAV` and `OVA01` count as OVA.
- Some Notion exports write a folder twice on disk. In such a Custom folder, a **Content** hit opened a page that showed the folder twice in its path and failed to load. The hit's title, the Search card's title and Aobana Reibun's lookup showed the folder twice too.
- A word typed with a Japanese input method in a Custom page's **Titles** box did not filter until the page was reloaded. It now filters when the word is confirmed.
- At phone width, scrolling a work's or folder's page swapped the search row's chips and the **Titles** | **Content** switch between lines, and switching between **Titles** and **Content** moved the list by a pixel or two.

## 2.3: Sort a file's sections

### Enhancements

- **Sort a file's sections.** The sort menu on a Custom file page now orders the file's sections, by title or by number of lines. A file opens in its own order until you sort it.

**Search**

- The kanji reading list that search by reading uses is updated: it gives readings for 46,170 kanji, where 2.2's gave 44,450.

**Media and Custom**

- **Most entries** and **Fewest entries** are offered only where they change the order: in **Media** when the titles listed hold different numbers of episodes, chapters or volumes, and in a Custom folder when its items hold different numbers of files.
- A card's context opens only the database of its own media: one for a manga or Custom line, where 2.2 opened all four.

**Library and indexing**

- An index run no longer reads the whole Sudachi dictionary (217 MB) to check it while the dictionary's size and modified time are as recorded.

**The page**

- Search results and the reader's lines no longer light up when the mouse passes over them or when they are tapped. Folders, section headers, menus and buttons still do.

### Bug Fixes

- With **Exact** on, a search by reading such as `行く＝ゆく` missed a word in a book when the book's furigana sat inside the word: 飛行(とびゆ)く, shown as 飛行く with its furigana.
- In a Custom folder, a new sort left the page where it was scrolled. It now goes to the top, as in **Media**.

## 2.2: Copy a sentence, and smaller search pages

### Enhancements

- **Copy a sentence.** A copy button on every Search card copies the sentence with its furigana, while furigana is shown, and the search match in bold, as Aobana Reibun puts it on a card. Pasted into Anki or another rich editor, the ruby and bold stay; pasted as plain text, the reading follows its word in （）.
- **Smaller, faster search pages.** A page of results is less than half the size it was, and **Longest** shows its first 100 cards sooner; more load 500 at a time as before.
- **Exclude one written form.** An exclusion in quotes, `-"なる"`, leaves out only the lines with なる written as it is; `-なる` still leaves out every form (なった, なって). On the Search tab and in a Custom title's box.

**Search**

- **Ruby only** searches by reading keep only the places whose reading the author's ruby gives. A place with no ruby, such as なま written in kana for `生＝なま`, is not kept.
- **Add context** on a subtitle card no longer reads every book and manga line when the first search finds it.
- Searches are still kept in memory while Aobana runs. The **Search cache** setting is gone, and the update deletes the cache file an older version made.

**Library and indexing**

- **Index library** with nothing changed no longer reads every file again: a file whose size and modified time are as recorded is skipped unread. After updating, the first run reads every file once more, to record them.
- Indexing loads the Sudachi dictionary once per process instead of twice, reads a changed file twice instead of three times, and writes less per line. A manga index run takes about a sixth less time, and the clean-up rules skip lines that need none of them.
- While a run goes on, the **Library** tab asks only for the log lines it has not shown yet.

**The page**

- The page font is downloaded again only when it changes, not at every update.

### Bug Fixes

- A known word imported from an Anki field whose `<ruby>` has a class was imported with no reading, so it never counted as known. Import such a list again.
- In the **Media** tab's search, a phrase in full-width quotes, as a Japanese keyboard types them, found its words apart, not the phrase.
- In a Custom title's own search box, `約束 -守る` left out only 守る as written. It now leaves out the same lines as the Search tab.
- With Anki open but busy, Aobana said Anki was not open. It now says Anki is not answering.
- One unreadable database, for example after a power cut, kept the **Library** tab at "Loading library information..." forever. The other media's figures now show.
- After an index run that stopped with an error, the **Library** tab blamed a closed window, even after a later run finished. It now says the run stopped with an error.
- During a subtitle index run, each "show more" in **Check library**'s results rebuilt the whole view.
- The **Copy** buttons of the Library log, the Guide and the update notice copied nothing on a page opened from another device, such as a phone on the same network.
- In a Custom title's boxes, the Enter that confirms a Japanese conversion could also start the search.
- Two numbers in **Settings** were written in the browser's number format, not the page's.
- On a phone, a menu wider than its button opened off the left edge of the screen, such as a file page's sort menu.
- On a phone, the search results could end in a screen of blank space after the keyboard was closed with the search box still selected.
- On a phone, Custom's sort stays at the right end. On the next line it sits under **Titles** / **Content**, one gap below it; docked at the top, it takes the switch's place.

## 2.1: Title counts that match the results

### Enhancements

- **Title counts match the results.** On the Search page, the number beside each title is the number of sentences its list shows, and **All** is their sum. A line that a title repeats, such as a line of the opening in every episode, counts once, except under **Chronological**, which lists every line.
- **Faster searches on a large library.** A new search takes over the search processes within about 2 seconds, instead of waiting for the one it replaces. A search by reading inside one title reads only that title's lines: under a second on a 142 GB test library, where 2.0 took 31 seconds.

**Search**

- **Index library** and **Optimize tables** mark the lines each title repeats, so the counts can leave them out without reading the text. The marks take about 6.7 MB for 53.6 million subtitle lines; on 12 processes the first build took 15 seconds for those lines and 2.5 minutes for 137 million book lines. Later runs redo only the titles whose files changed.
- Until **Optimize tables** has run, a picked title's count can include its repeated lines; a note under the search bar then gives its number of sentences.
- After a search, Aobana stays ready for the next one for 1 minute, not 5, so the memory it holds for that (about 1.3 GB with 12 search processes) is freed sooner.
- A search that only excludes words, like `ーっ`, says so and how to search for it, instead of finding nothing.

**Library and indexing**

- After updating from 2.0, press **Optimize tables** in the **Library** tab once to build the marks; a notice asks for it. From 1.9, run **Check library**, then **Index library**.
- When the recommendations of **Check library** are not saved yet, **Index library** first says how many duplicates and files the check recommends leaving out and how many subtitles to read again, and which buttons save them. **See check results** goes to them; **Index anyway** carries on.
- **Convert to UTF-8** keeps each original file at its own folder and name inside the `backups/encoding` folder of Aobana's data folder, such as `backups/encoding/Show/ep01.srt.bak`.
- **Index library** shows the marking as **Finding repeated lines...** with the lines done, and its time estimate counts it.
- Where the Library's progress shows two numbers, it says what they count: lines or files.
- The notice asking for **Optimize tables** says what the index gains, appears again for a later version that needs it, and its **Open Library** button goes straight to **Optimize tables**.
- Updating from 1.9, the notice asking for **Index library** also says that the **Media** tab's subtitle list appears once it has run.
- Backups made by 2.0's **Convert to UTF-8** move to the new folders at start, file by file, while the page is already open.

**Media and the page**

- On a phone, the sheet of titles on the Search page is 65% of the screen high, not 85%.
- The **Media** list shows "Loading..." until its first answer.

### Bug Fixes

- Under **All**, a line found in two titles was listed once, under the first title only.
- On an index from before 2.0, not yet rebuilt by **Index library**, each search process first read every line with ruby before searching: on a 142 GB test library, over 21 minutes and 11 GB of memory each.
- The time left for a search by reading was guessed from the database's size: on a 142 GB test library it said 840 seconds at the start and rose to 1,121. It now follows the search: about 65 seconds at the start of a search that takes 110.
- A search by reading for an adjective, like `辛い＝からい`, also found its stem in kana where those kana were another word, such as the から of 暑いからさ. Inflected forms in kana, like からそう or からすぎる, are still found.
- A search in kana left the kanji it found unmarked when the book gave each kanji of the word its own ruby: かみ in 紙吹雪 (かみふぶき).
- A manga series or a Custom folder picked before searching could leave out a few volumes or files that **Index library** had read again.
- With nothing searched, **All** in the title list showed 0.
- On a phone, the search box's example did not fit in the box. It is now `見る, 丸=がん, 飲む -酒`.
- On a phone, the changelog window's buttons were at the very end of the changelog. They now stay at the top beside its title, and the text scrolls under them.
- On a phone, the scrollbar of the title sheet ran past its rounded top corner.
- With Custom on, **Index library** took longer with every `.txt` and `.md` file even when none had changed, growing with the square of their number: 25.6 seconds for 16,000 files, now 6.4.
- In **Media**, Custom's **Content** search and the search in a file did not take `ー` before a word as an exclusion, `- ない` as one exclusion, or a compatibility kanji such as U+FA5B as its ordinary form, 者 (U+8005).
- A title's page in **Media** waited for the Media list's count before listing its episodes, chapters or volumes: after an index run, until the whole list was counted, and on an index from before 2.0, forever.
- On an index from before 2.0, the **Media** list asked Aobana for its state every 0.7 seconds for as long as the page was open, in a background tab too.
- **Convert to UTF-8** refused a file when an earlier backup of it did not match. Another original at the same path is now kept beside the first, as `ep01.srt (2).bak`.
- `/api/search` with an empty query and a Custom title answered with an error instead of the title's lines.

## 2.0: i+1 sentences, search by reading, and Custom

### Enhancements

- **i+1 sentences.** Load the words you know (a word list, an Anki export, Jiten, Migaku, or your Anki decks through Aobana Reibun 1.2). **i+1 first** and **i+1 only** bring forward the sentences where the searched word is the only one you don't know, and each result shows how many of its words you know.
- **Search by reading.** Join a word and its reading to find only that reading: `好く＝すく`, or `丸＝がん`, which also finds 弾丸. **Ruby only** keeps the lines where the reading is the author's own furigana.
- **Custom.** Your own `.txt` and Markdown (`.md`) files are a fourth media, searched and read like the others. Each folder is a category, and a Notion export keeps its pages' order.
- **Several folders per media.** Each media can read from more than one folder, added and removed in **Settings**.
- **Library check.** Duplicates are grouped with one recommended copy each, subtitles that are not UTF-8 can be converted with a backup kept, and nothing is saved until you press **Save choices** or indexed until you press **Index library**.
- **Open in Media.** The Media icon on a search result opens the Media reader at that line.

**Search**

- **i+1** has its own menu beside the sort, shown once a known-word list is loaded. Under **Recommended**, **i+1 first** lists the i+1 sentences, then those with one other unknown word, then two. For a word you already know, an i+1 sentence is one with a single other unknown word.
- Every result shows its known words (**5/8 known**) when a list is loaded, with i+1 off too. A switch in **Settings** hides the counts.
- Search by reading takes a dictionary form (`行った＝おこなう` searches 行う), a leading kana (`お茶＝ちゃ`), and readings with pitch marks or dots (`たべ↓る`, `た・べる`). A reading guessed by the dictionary rather than written by the author is underlined with dots.
- A search by reading looks only at the lines that hold the word's kanji, so it stays fast. 2.0's index is about 8% larger than 1.9's.
- A search right after another one starts faster: Aobana stays ready for 5 minutes after the last search.
- Extra spaces, full-width spaces, and spaces after `-` or around `＝` no longer change a search.
- In a Japanese query, `ー` (the long-vowel mark, which the `-` key types with Japanese input on) before a word excludes it like `-`, so there is no need to switch to half-width.
- Recent searches each have a ✕ to remove them; 20 are kept.
- A result's context shows the 3 lines before and after it, in every media.

**Known words**

- **Settings** has a **Known words** card: import a list with a preview and a choice of column, see your lists, and remove one.
- **Import from Anki** reads your decks through Aobana Reibun 1.2 while Anki is open: choose the decks, which cards count (mature at 21 days by default) and each note type's word and reading fields, with a live count. **Update from Anki** reads the same choice again.

**Custom**

- An Explorer-style browser with a Titles and Content search, a reader with ★ on each line, and a sort menu.
- `漢字(かな)` written in a text file is shown as furigana and searchable by its reading; a switch in **Settings** turns it off.
- Spaces at the start and end of each line are trimmed by default; a switch in **Settings** keeps them.
- Markdown headings are sections; marks, links, images and table borders are left out.
- **Check library** finds Custom's duplicates, files with no Japanese, bilingual files, and files that are empty or have no line breaks.

**Library and indexing**

- Subtitles are read strictly as UTF-8, UTF-16, Shift-JIS, EUC-JP or ISO-2022-JP, by their real format whatever the extension, and **Check library** says why a file can't be read.
- **Convert to UTF-8** first saves the original files to the `backups` folder in Aobana's data folder, and the window shows its full path. Uninstalling never deletes it.
- On Windows, uninstalling can now also delete the Manga and Custom folders and your known words. One box ticks every media folder. A folder you chose yourself is never deleted.
- **Index library** shows its phase and the time left.
- Files you marked in **Check library** to be read again are listed, and the next **Index library** reads them.
- The time estimate before indexing counts the files to read again, and manga and Custom too.
- A media's folders are read in the order listed. A file at the same path in two of them is read from the first, and **Check library** lists it.
- A folder can't be added if it is, holds or sits inside another media's folder; the message names that folder.
- A media turned off in **Settings** is never indexed or checked.

**Reading files**

- Subtitles with HTML ruby show it as furigana.
- A subtitle's full-width `漢字（かな）` is drawn as furigana where it reads as one.
- `.ass` times are read as a video player reads them, and a line that ends at or before its start is left out.
- ♫, ♩ and 🎵 lines are left out like ♪; dashes, middle dots and runs of dots are stored in one form.
- Chinese credits and notes are left out, and a Japanese line with one simplified character is kept.
- Books: contents pages label chapters better, and when two quotes share a paragraph (「…。」「…」), each is its own line.
- A book whose pages are copy-protected (DRM) is listed by **Check library**, not indexed.
- Manga: furigana that the OCR read as part of the line is shown as furigana again.

**Media and the page**

- Media remembers where you were, and a show's seasons, OVAs and films are grouped.
- Every Media detail page has a path bar with ← and →, docked under the top bar while you scroll.
- A Media page ends with "No more results" once nothing more is loading.
- On a phone, the Search page's titles open in a sheet from the bottom, and the search row hides while scrolling down.
- Esc closes every window the way its **Cancel**, **Later** or **Close** button does, so nothing starts or changes by accident.
- The **Guide** has a **Contents** button and sections for i+1 and Custom.

### Bug Fixes

- **Stop** did not reach a run that was still reading files, cleaning up or optimizing tables, and indexing processes could outlive Aobana. **Stop** now answers within a second and keeps everything indexed up to there; the next **Index library** carries on from where it stopped.
- A search during an index run could show no results instead of saying the index is busy.
- On a large library, **Check library** sent its whole report to the page (341 MB on a 128,000-file test library), which froze it while loading. The results now come as counts, and each list's rows 200 at a time.
- A query of symbols alone, like `♪`, found nearly every line instead of the lines that hold it.
- An `=` in a query was dropped, so `2+2=4` found unrelated lines.
- A word typed alone could be searched as another word: 好く found いい and よい.
- **Chronological** listed a show's files by file name, so its seasons, OVAs and films were mixed. They now follow the Media tab's order.
- A tap on a button, tab or menu could open Yomitan.
- Books: text placed directly on a page, outside a paragraph, was not read.
- A long sentence searched as typed often found nothing, while the same sentence ending in 。 found it.
- A search with an exclusion that held the searched word, like `チェーン -チェーンロック`, dropped every line.
- A word split by a symbol was found as the word: `海賊船` found （海賊）船.
- A `"` inside a word made the search find nothing.
- With **Exact** ticked, `?` and `!` typed half-width found no subtitle line.
- Opening a line in a very large book index could take minutes.
- macOS `._` files showed as empty episodes.
- Captions written inside `[…]` were not read.
- A book with a placeholder title, or a title wholly in square brackets, showed an empty title.
- Book titles with `～` or `－` were sorted as if those were missing.
- After a re-index, only the first 5,000 Favorites were matched to their lines in the new index.
- **Optimize tables** was offered for media that **Index library** reads again anyway, and "Table optimization finished." appeared twice.
- An update download without a SHA-256 digest was installed unchecked; it is now refused before it is downloaded.

## 1.9: Open folder scrolls to the file

### Enhancements

- Updating from inside Aobana works from 1.4 or newer. The code that only moved files and settings from 1.3 and older is removed; on an older version, install 1.9 from the release page.

### Bug Fixes

- **Open folder** on Windows scrolls to the selected file, which 1.8 could leave out of view.
- **Open folder** on a show's or manga series' page opens the deepest folder that holds all its files, so a show kept in a single season folder opens that season folder.
- The folder icon on a title's episode and volume rows in **Media** sits level with the row's arrow.

## 1.8: Open folder from Media and Search

### Enhancements

- **Open folder.** A title's page in **Media** has an **Open folder** button that opens the folder holding the title. A folder icon on each episode or volume, and on each Search result, opens its folder with that file selected, ready to open in the program you choose. On Linux the folder opens without the file selected, and on Termux the buttons are hidden.

### Bug Fixes

- The Japanese **Guide** names Anki's menu 「ツール」, as a Japanese Anki shows it, in the Aobana Reibun section.

## 1.7: Safer indexing, duplicate selection, and organized source code

### Enhancements

- **Aobana Reibun.** A new Anki add-on fills cards with example sentences and media from Aobana, Nadeshiko and Immersion Kit. The **Guide** tab's **Anki add-on: Aobana Reibun** section explains how to install it.
- **Safer library indexing.** When more than half of a media library's indexed files are missing, Aobana pauses their removal and asks you to confirm. A file that is present but cannot be read keeps its existing index and is tried again on the next run.
- **Duplicate selection.** **Select all** selects duplicate copies while keeping the chosen original. The button changes to **Deselect all** when every eligible file is selected.
- Furigana rendering handles long sentences in linear time, with the same displayed text and readings.
- Library progress uses structured events so filenames and titles containing line breaks do not interrupt progress reporting.
- The source code is organized into an `aobana` package, with separate search, indexing, and server modules. Run from source with `python -m aobana`.
- Page styles, translations, and scripts are separate files that the browser can cache.

### Bug Fixes

- **Remove anyway** retries only the media whose missing files were held for confirmation.
- Parallel search workers leave the update check and library warm-up to the server.
- Imported and stored Favorites keep supported fields and safe furigana markup.
- Search treats `%` and `_` in excluded terms literally, and title filters match the selected folder exactly.
- Concurrent Settings changes preserve each saved value, and resetting search caches clears title counts too.
- Book titles stored with escaped characters such as `&#12354;` display as text, and image-only books whose pages are all labelled `page` are listed as image-only instead of indexed as text. To find them, **Check library** reads books of up to 200 sentences once more after the update; a 46,859-book test library held 6.
- Request threads release furigana database connections and share a bounded tokenizer pool.
- On Termux, folder paths remain visible while unsupported **Open folder** buttons are hidden.
- Updating from 1.6 removes the earlier root program files. Windows, macOS, Linux, and Termux launchers use the package entry point.

## 1.6: One-time table optimization, image-only book filtering, and faster Settings

### Enhancements

- **Optimize tables** appears beside **Index library** only when an existing subtitle, book, or manga database needs its display-length or furigana lookup table. It includes databases for media turned off in Settings and reads the existing index without rereading files. New libraries and indexes with complete tables do not show the button.
- **Image-only books.** **Check library** lists `.epub` files with no extractable text under **Image-only (no text)** so they can be excluded from the index. **Index library** automatically excludes zero-sentence files and checks them again if they change. Previously short books are read again once to recover chapters missed by older EPUB reading rules; established long books keep their index and library-check cache.
- **Updating an existing library.** After the normal What's New screen, returning users with a database see a one-time reminder to run **Check library**, review its findings, and then run **Index library**. Books with 30% to 50% Japanese among language-bearing lines appear under **Review language** and are left unticked for a decision. **Left out of the index** groups excluded files by the same categories as the check above, and each section has **Select all**.
- The table build uses the chosen indexing worker count, up to all detected CPU threads. The first-use indexing speed popup has been removed; the worker control remains below the Library buttons.
- Settings shows its saved values immediately from a snapshot beside the databases, then refreshes them from the live app.

### Bug Fixes

- The EPUB reader recovers previously short books whose prose sits directly inside `<body>` or in `<span>` and `<br>` runs, and resolves chapter or table-of-contents paths with `..` relative segments (recovering 91 previously empty books — 348,997 sentences across 1,119 chapters — in a measured test library).
- Generic image labels are no longer counted as book sentences. Files already left out of the index remain excluded until restored in Library.
- Table optimization uses the current indexer code when Aobana is started with packaged Python, so it no longer stops after building display lengths because an older furigana helper was loaded.

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
