    const GUIDE = {
      ja: `
        <h1>ガイド</h1>
        <p class="lead">露草（あおばな）の使い方。</p>

        <h2>露草とは</h2>
        <p>自分の持っている字幕ファイル・電子書籍・漫画・カスタムのテキストから、日本語の例文を検索するアプリです。すべてこのパソコンの中で動き、インターネットには何も送りません（起動時に新しいバージョンがあるかを GitHub に確認し、更新を選んだときだけダウンロードします）。検索は語の活用形や読みにも対応していて、例文はふりがな付きで表示されます。</p>

        <h2>1. ファイルを入れる</h2>
        <p>読み込まれるのは <code>.srt</code>・<code>.ass</code>・<code>.ssa</code>（字幕）、<code>.epub</code>（電子書籍）、<code>.mokuro</code>（漫画）、<code>.txt</code>・<code>.md</code>（カスタム）です。<code>.pdf</code> などは無視されます。<code>.ass</code> は日本語の台詞だけを読み込みます（中国語・英語の行、多くの看板、図形は除き、認識できた小さなルビ行は台詞に付けます。特殊な配置ではルビを読み取れないことがあります）。フォルダの場所は<a href="/?tab=settings">設定</a>タブで確認・変更できます。使わないメディアはそこでオフにできます。</p>
        <pre>字幕フォルダ/
├─ 作品A/
│   ├─ 作品A S01E01.srt
│   └─ 作品A S01E02.srt
└─ 作品B/
    └─ 第1期/                  ← 作品フォルダの中なら、さらに分けてもOK
        └─ 作品B 第01話.srt

書籍フォルダ/
├─ [著者] 書名.epub
└─ 好きなサブフォルダ/
    └─ [著者] 書名.epub

漫画フォルダ/
└─ シリーズA/
    ├─ シリーズA 01.mokuro
    └─ シリーズA 02.mokuro

カスタムフォルダ/
└─ 歌詞/                      ← フォルダ名がカテゴリ名になる
    ├─ 曲A.txt
    └─ メモ.md</pre>
        <ul>
          <li><b>字幕は作品ごとにフォルダを作ってください。</b>一番上のフォルダ名が作品名になります。字幕フォルダの直下に置いた字幕ファイルは、ファイル名を作品名とする1つの作品として読み込まれます。</li>
          <li>話数はファイル名の <code>S01E02</code>、<code>第2話</code>、<code>- 02</code> などから読み取ります。</li>
          <li>書籍の題名と著者は EPUB のメタデータから取ります。メタデータがない場合は、ファイル名 <code>[著者] 書名.epub</code> から取ります。</li>
          <li><b>漫画はシリーズごとにフォルダを作ってください。</b>フォルダ名がシリーズ名、ファイル名が巻の名前になります。<code>.mokuro</code> は <a href="https://github.com/kha-white/mokuro" target="_blank" rel="noopener">mokuro</a> が漫画の画像を OCR して書き出すファイルです。Aobana はその文字だけを読むので、画像はなくても構いません。文字は mokuro が読み取ったままなので、読み間違いや読み落としはそのまま表示されます。</li>
          <li><b>カスタムはカテゴリごとにフォルダを作ってください。</b>一番上のフォルダ名がカテゴリ名になります。1行ずつ検索でき、空行は段落（歌詞なら連）の区切りになります。漢字の後ろに書かれたかなの読み（漢字(かな)・漢字（かな）・漢字《かな》、｜で始まる語）はふりがなで表示します。<b>設定</b>タブのカスタムフォルダの下でオフにできます。<code>.md</code> では見出しが区切りになり、強調などの記号、リンク先、画像、表の罫線は除いて文字だけを読みます。表の行と入れ子のリストは1行ずつ読みます。親ページに子ページのリンクが並んでいる場合は、その順番で表示します。</li>
        </ul>

        <h2>2. インデックスを作成する</h2>
        <p><a href="/?tab=library">ライブラリ</a>タブで「インデックス作成」を押すと、すべての文を解析して検索用のデータベースを作ります。大きなライブラリでは数分以上かかることがあります。進行状況には処理段階と保存済みのファイル数が表示されます。「中止」しても保存済みの結果は残り、同じ操作を実行すると続きから処理できます。2回目以降は追加・変更・削除されたファイルだけを処理します。ファイルを入れ替えたら、もう一度押してください。</p>
        <p>1つのメディアだけをインデックスするには、ほかのメディアを設定タブでオフにします。字幕・書籍・カスタムのファイルが増えるときは、作成前にデータベースの大きさと所要時間の見積もりが出ます（漫画だけのときは見積もりなしですぐに始まります）。データベースの合計が 10 GB を超えそうなときは、検索が遅くなるため、始める前に確認が表示されます。同じタブの「点検する」では、字幕・書籍・カスタムから日本語以外のファイルや重複ファイルを探し、選んだものをインデックスから外せます（ファイルは移動も削除もしません）。二か国語の字幕は日本語の部分だけがインデックスされます。</p>

        <p>字幕は UTF-8、BOM 付き UTF-16、Shift-JIS、EUC-JP、ISO-2022-JP に対応し、時刻の小数点はカンマとピリオドの両方を読めます。拡張子が .srt でも ASS の内容を認識します。「点検する」で、一部を読めなかったファイル、読めないファイル、日本語の行がないファイルを確認できます。「次回の対象にする」は一覧の字幕を次の「インデックス作成」で読み直す対象として保存します。押しただけではインデックスは始まりません。「UTF-8 に変換」は元のファイルをバックアップしてから変換し、もう一度点検します。検索への反映には「インデックス作成」が必要です。「最適化する」は、ファイルを読み直さずに検索用の表を準備します。</p>
        <p>重複は組ごとに、残すファイル・「全て残す」・「未選択」のどれかを選びます。「適用」はその組でおすすめのファイルを選び、「おすすめをまとめて適用」は未選択の組すべてで選びます。もう一度押すと、その操作で選んだものだけを取り消します。ほかの一覧では、インデックスに残したいファイルのチェックを外します。最後に「選んだ内容を保存」で保存してください。戻すときは保存済みの一覧で選び、「チェックしたファイルを再び対象にする」で保存します。検索に反映するには、その後「インデックス作成」を実行してください。字幕は双方の台詞の 90% 以上（書籍は文の 50% 以上）が一致するとき、または SubPlz の組か同じ内容のファイルのとき、重複とみなします。おすすめ以外のファイルを残すには、そのファイルが組のすべてのファイルと同じように一致する必要があります。</p>
        <h2>3. 検索する</h2>
        <ul>
          <li><b>語形はまとめて検索されます。</b><code>食べる</code> で「食べた」「食べて」なども見つかります。ひらがなの <code>たべる</code> でも検索できます。</li>
          <li><b>完全一致</b> — 入力した形そのままで探します。<code>"食べて"</code> のように <code>"</code> で囲んでも同じです。</li>
          <li><b>除外</b> — 検索語の前に <code>ー</code>（伸ばし棒）を付けると、その語を含む行を除きます。日本語入力のまま <code>-</code> キーで入力でき、半角の <code>-</code> でも同じです。<code>ー</code> の前にはスペースを入れます。例えば <code>チェーン ーチェーンロック</code> は「チェーンロック」を含む行を除いて検索します。いくつでも重ねられ、<code>食べる ー食べない ー食べたい</code> は「食べない」「食べなかった」「食べたい」などの形を除きます。</li>
          <li><b>読みで検索</b> — 語と読みを <code>＝</code> でつなぐと（半角の <code>=</code> でも可）、その読みの箇所だけを探します（例: <code>好く＝すく</code>。<code>丸＝がん</code> は弾丸の丸も見つかります）。除外にも使えます（<code>ー行く＝ゆく</code>）。ルビのない箇所の読みは Sudachi の推定で、点線の下線が付きます。同じ作品のほかの箇所にルビがあれば、その読みを使います。</li>
          <li><b>ルビのみ</b> — 読みで検索するとき、ルビで読みが分かる箇所だけを残します。</li>
          <li><b>並べ替え</b> — おすすめ（読みやすい長さ順）、時系列順、長い順、短い順、ランダム。選んだ並べ替えは次回も使われます。</li>
          <li><b>全て / 字幕 / 書籍 / 漫画 / カスタム</b> — サイドバーの上のボタンで、検索対象を切り替えます。これも記憶されます。オンのメディアが2つのときは「両方」と表示されます。</li>
          <li><b>作品で絞り込む</b> — サイドバーの作品名を押すと、その作品の中だけを検索します。いくつでも選べ、もう一度押すと外れます。</li>
        </ul>

        <p>検索ページの検索はタブを切り替えても続きます。メディアで新しい本文検索をすると置き換わりますが、作品一覧の閲覧や絞り込みでは止まりません。インデックス作成、表の準備、データベースの移動・削除では検索を停止して更新します。ファイルを読むだけの点検では検索は止まりません。</p>
        <h2>既知語と i+1</h2>
        <p>知っている語のリストを読み込むと、並べ替えの横に i+1 のメニューが出ます。i+1 の例文は、知らない語が1語だけの文です。その1語は検索した語で、検索した語を知っているときはほかの語です。かなで検索すると、その読みの文だけが入ります（からい なら、つらい と書いた文は入りません）。「i+1 を優先」はそれを上に並べます（おすすめ順では、そのあと知らない語の少ない文から）。「i+1 のみ」はそれだけを表示します。1語で検索すると、i+1 がオフでも、各例文に「既知 5/8」のように知っている語の数が出ます（助詞などは数えません）。i+1 の例文は数字の色が変わります。設定でこの数を消すと、i+1 の例文にだけ「i+1」と出ます。リストは<a href="/?tab=settings">設定</a>タブの「既知語」で読み込みます。</p>
        <ul>
          <li><b>ファイルから</b> — 1行に1語のテキスト、Anki の「ノートをテキストで書き出す」で保存したファイル、Jiten と Migaku の書き出しを読めます。読み込む前に、語と読みの列を確かめられます。</li>
          <li><b>Anki から</b> — Anki と Aobana Reibun が開いていれば、「Anki から取り込む」でデッキを選べます。既定では間隔 21 日以上の成熟したカードの語を取り込みます。あとで「Anki から更新」を押すと、同じデッキを読み直します。Anki を閉じても、取り込んだリストはそのまま使えます。</li>
        </ul>
        <h2>例文の操作</h2>
        <ul>
          <li><b>★</b> お気に入りに保存します。<a href="/?tab=saved">お気に入り</a>タブで見られます（このブラウザに保存されます）。</li>
          <li><b>⋯</b> 前後の文脈を表示します。</li>
          <li><b>ふ</b> ふりがなの表示・非表示を切り替えます。</li>
        </ul>

        <h2>メディア</h2>
        <p><a href="/?tab=media">メディア</a>タブには、インデックス済みのすべての作品・書籍・漫画・カスタムのカテゴリが一覧で表示されます。作品を開くと、各話・各章・各巻を最初から順に読めます。漫画の文にはページ番号が付きます。ページ番号を押すとそのページが開き、← で次のページ、→ で前のページへ進みます。巻の終わりでは次の巻へ続きます。「← メディア一覧」とブラウザの戻る操作では、絞り込み、並び順、読み込んだ一覧とスクロール位置を復元します。他のタブから戻ると現在のメディア画面を保ちます。字幕の期はフォルダ名・ファイル名の明確な手掛かりでまとめ、判別できる OVA・劇場版もグループにします。判別できない話は通常の行で表示します。グループが1つなら開き、複数なら閉じた状態で始まります。戻ったときは開閉状態を復元します。上部の選択中のメディア・検索アイコンを押すと、そのページの先頭へ移動できます。</p>

        <p><b>Q</b> で、検索・メディア・お気に入り・ライブラリの表示中の検索欄や絞り込み欄に移り、入力内容を選択できます。</p>
        <h2>ショートカット</h2>
        <p><span class="kbd-key">Q</span> 検索バー · <span class="kbd-key">D</span>/<span class="kbd-key">↓</span> 次へ · <span class="kbd-key">A</span>/<span class="kbd-key">↑</span> 前へ · <span class="kbd-key">C</span> 文脈 · <span class="kbd-key">S</span> お気に入り · <span class="kbd-key">F</span> ふりがな · <span class="kbd-key">?</span> ヘルプ · <span class="kbd-key">Esc</span> 閉じる</p>

        <h2 id="reibun">Anki アドオン: Aobana Reibun</h2>
        <!--reibun-->
        <p>Aobana Reibun（例文）は、Anki のカードに日本語の例文を入れるアドオンです。Aobana を使うと、手持ちの字幕・書籍・漫画・カスタムのファイルから例文を選び、ふりがな、作品名、前後の文脈を、漫画ならそのページの画像も一緒に入れます。Aobana が動いていなければアドオンが起動し、終わったら止めます。</p>
        <ul>
          <li><b>まとめて入れる</b> — Anki の「ツール → Aobana Reibun → Run」でデッキ全体に、ブラウザでは選んだノートに入れます。フィールドが埋まっているときは、スキップ・置き換え・追加から選べます。</li>
          <li><b>復習中に1枚ずつ</b> — <span class="kbd-key">Ctrl+Shift+W</span> を押すと、今のカードに Aobana の例文が入ります。</li>
          <li><b>ほかの2つのソース</b> — Nadeshiko（API キーが必要）と Immersion Kit（キー不要）の例文も、スクリーンショットと音声つきで入れられます（<span class="kbd-key">Ctrl+Shift+O</span>・<span class="kbd-key">Ctrl+Shift+K</span>）。</li>
          <li><b>i+1 の既知語</b> — Anki が開いている間、Aobana はアドオンを通してデッキの語を読めます。<a href="/?tab=settings">設定</a>の「既知語」で「Anki から取り込む」を押します。Anki の中身は変わりません。</li>
        </ul>
        <p>Anki の「ツール → アドオン」で「アドオンを入手...」を押し、上のコードを入力するとインストールできます。AnkiAutoImage のコードから作り始めました。</p>

        <h2>表示と設定</h2>
        <p>右上のボタンでショートカット一覧（?）、言語（日本語 / English）、テーマ（紙・霞・夜・深夜）を切り替えられます。</p>

        <h2>アプリの終了</h2>
        <p>Aobana は「露草 / Aobana」という名前のウィンドウ（macOS と Linux ではターミナル）で動いています。終了するにはそのウィンドウを閉じます。ブラウザのタブを閉じるだけでは止まりません。</p>
      `,
      en: `
        <h1>Guide</h1>
        <p class="lead">How to use Aobana (露草).</p>

        <h2>What Aobana is</h2>
        <p>An app for searching Japanese example sentences in the subtitle files, e-books, manga and text files you own. Everything runs on this computer, and nothing is sent to the internet (at start it asks GitHub whether a newer version exists, and downloads one only when you choose to update). Searches understand conjugations and readings, and sentences are shown with furigana.</p>

        <h2>1. Add your files</h2>
        <p>Aobana reads <code>.srt</code>, <code>.ass</code> and <code>.ssa</code> (subtitles), <code>.epub</code> (e-books), <code>.mokuro</code> (manga), and <code>.txt</code> and <code>.md</code> (Custom). Other formats, including <code>.pdf</code>, are ignored. From an <code>.ass</code>, only the Japanese dialogue is read: Chinese and English lines, most signs and drawings are left out; recognized small furigana lines are attached to their dialogue. Unusual layouts may lose ruby. The <a href="/?tab=settings">Settings</a> tab shows where the folders are and lets you change them, or turn off a media you don't use.</p>
        <pre>Subtitles folder/
├─ Show A/
│   ├─ Show A S01E01.srt
│   └─ Show A S01E02.srt
└─ Show B/
    └─ Season 1/                ← sub-folders inside a show folder are fine
        └─ Show B 第01話.srt

Books folder/
├─ [Author] Title.epub
└─ any sub-folder/
    └─ [Author] Title.epub

Manga folder/
└─ Series A/
    ├─ Series A 01.mokuro
    └─ Series A 02.mokuro

Custom folder/
└─ Lyrics/                     ← the folder's name becomes the category
    ├─ Song A.txt
    └─ Notes.md</pre>
        <ul>
          <li><b>Give each show its own folder.</b> The top folder's name becomes the show's name. A subtitle file placed directly in the subtitles folder is read as a show of its own, named after the file.</li>
          <li>Episode numbers are read from file names such as <code>S01E02</code>, <code>第2話</code> or <code>- 02</code>.</li>
          <li>A book's title and author come from the EPUB's metadata, or, when that is missing, from the file name <code>[Author] Title.epub</code>.</li>
          <li><b>Give each manga series its own folder.</b> The folder's name becomes the series' name, and each file's name its volume's. A <code>.mokuro</code> file is what <a href="https://github.com/kha-white/mokuro" target="_blank" rel="noopener">mokuro</a> writes when it runs OCR on manga pages. Aobana reads only its text, so the images are not needed. The text is shown as mokuro read it, misread or missed words included.</li>
          <li><b>Give each Custom category its own folder.</b> The top folder's name becomes the category's name. Each line is searchable, and a blank line separates paragraphs (a lyric's verses). A kana reading written after a kanji word (漢字(かな), 漢字（かな）, 漢字《かな》, or a word that starts with ｜) shows as furigana; turn this off under the Custom folder in the <b>Settings</b> tab. In an <code>.md</code> file, headings create sections, and only the text is read: formatting marks, link addresses, images and table borders are left out. Each table row and each item of a nested list is read as one line. When a parent page lists links to its subpages, that order is used.</li>
        </ul>

        <h2>2. Build the index</h2>
        <p>Press "Index library" in the <a href="/?tab=library">Library</a> tab. Every sentence is analyzed into a search database; a large library can take much longer than a few minutes. Progress shows the current phase and committed files. Stop keeps completed work; run the same operation again to continue. Later runs only process files that were added, changed or removed, so run it again whenever your files change.</p>
        <p>To index one media only, turn the others off in the Settings tab. When subtitles, books or Custom files were added, you first see how large the databases will get and how long it will take (manga alone starts at once, with no estimate); past 10 GB in total, Aobana asks before it starts, as searches get slower. "Check library" in the same tab finds subtitles, books and Custom files that are not Japanese, and duplicates, and leaves the ones you tick out of the index (nothing is moved or deleted). Bilingual subtitles are indexed with their Japanese part only.</p>

        <p>Subtitles can be UTF-8, UTF-16 with a BOM, Shift-JIS, EUC-JP or ISO-2022-JP. Times with a comma or a dot are both read, and an ASS file named .srt is still read as ASS. Check library lists files it could not read fully, files it cannot read, and files with no Japanese lines. "Add to next index" marks the listed subtitles to be read again at the next "Index library"; it does not start indexing. "Convert to UTF-8" keeps a copy of each original file, converts it, and checks the library again. Run "Index library" afterwards to update search. "Optimize tables" prepares the search tables without reading your files again.</p>
        <p>For each group of duplicates, choose the file to keep, "Keep all" or "Not chosen". "Apply" chooses the recommended file for its group, and "Apply all recommendations" does so for every group not yet chosen; pressing either again undoes only what that press chose. In the other lists, untick any file you want to keep in the index. Then save with "Save choices". To restore files, select them in the saved list and save with "Include the ticked files again". Run "Index library" afterwards to update search. Two subtitle files are copies when at least 90% of their lines match both ways (books: 50% of sentences), or when they are a SubPlz set or the same file. To keep another copy than the recommended one, it must match every file of its group that way.</p>
        <h2>3. Search</h2>
        <ul>
          <li><b>Search conjugated forms.</b> <code>食べる</code> also finds 食べた, 食べて and so on, and the reading <code>たべる</code> works too.</li>
          <li><b>Exact</b> matches exactly what you typed. Wrapping the query in quotes (<code>"食べて"</code>) does the same.</li>
          <li><b>Exclude</b>: put <code>-</code> before a word, after a space, to exclude lines containing it. With Japanese input on, the same key types <code>ー</code>, the long-vowel mark, and that works too. For example, <code>チェーン -チェーンロック</code> searches for チェーン without チェーンロック. Exclusions stack: <code>食べる -食べない -食べたい</code> leaves out forms such as 食べない, 食べなかった and 食べたい.</li>
          <li><b>Search by reading</b>: join a word and its reading with <code>＝</code> or <code>=</code> to find only that reading (<code>好く＝すく</code>; <code>丸＝がん</code> also finds 弾丸). Exclusions take a reading too (<code>-行く＝ゆく</code>). Without ruby, the reading is Sudachi's guess, shown with a dotted underline; if the same work gives the word ruby elsewhere, that reading is used.</li>
          <li><b>Ruby only</b>: in a search by reading, keeps only matches whose reading is in the ruby.</li>
          <li><b>Sort</b>: recommended (easy-to-read lengths first), chronological, longest, shortest, random. Your choice is remembered.</li>
          <li><b>All / Subs / Books / Manga / Custom</b>: the buttons at the top of the sidebar choose what to search. Also remembered.</li>
          <li><b>Filter by title</b>: click a title in the sidebar to search inside it only. You can pick several; click one again to remove it.</li>
        </ul>

        <p>A Search page query keeps running when you change tabs. A new content search in Media replaces it; browsing or filtering the title list does not. Indexing, table preparation and moving or deleting a database interrupt searches so the database can be updated. Check library only reads your files and does not interrupt a search.</p>
        <h2>Known words and i+1</h2>
        <p>Import a list of words you know, and an i+1 menu appears beside the sort. An i+1 sentence has one word you don't know: the one you searched, or another word if you already know that one. Search in kana and only that reading counts: からい leaves out lines that write つらい. "i+1 first" puts those sentences on top (under Recommended, then the ones with the fewest unknown words); "i+1 only" shows just them. Search one word and each sentence shows how many of its words you know, like "5/8 known", even with i+1 off (particles and the like don't count). On an i+1 sentence the number is colored. Turn the counts off in Settings and only the i+1 sentences are marked, with "i+1". Lists are imported in <a href="/?tab=settings">Settings</a> under "Known words".</p>
        <ul>
          <li><b>From a file</b>: one word per line, a file saved with Anki's "Notes in Plain Text" export, or a Jiten or Migaku export. Before importing, you can check which columns hold the word and its reading.</li>
          <li><b>From Anki</b>: with Anki open and Aobana Reibun installed, "Import from Anki" lets you pick decks. By default it takes the words of mature cards, with an interval of 21 days or more. "Update from Anki" reads the same decks again later. The imported list keeps working with Anki closed.</li>
        </ul>
        <h2>Sentence buttons</h2>
        <ul>
          <li><b>★</b> saves it to the <a href="/?tab=saved">Favorites</a> tab (stored in this browser).</li>
          <li><b>⋯</b> shows the surrounding context.</li>
          <li><b>ふ</b> shows or hides furigana.</li>
        </ul>

        <h2>Media</h2>
        <p>The <a href="/?tab=media">Media</a> tab lists every indexed show, book, manga series and Custom category. Open one to read its episodes, chapters or volumes in order; manga lines carry their page number. Click it to open that page: ← turns to the next page and → to the previous one, on into the next or previous volume. "← All media" and browser Back restore your list filter, sort, loaded titles and scrolling position. Returning from another app tab keeps the current Media view. Subtitle seasons use explicit folder or filename clues, with OVA and film groups when recognized. Unclassified episodes stay as ordinary rows. One group opens by default; multiple groups start collapsed, and your open groups restore on return. Click the active Media or Search icon at the top to scroll that page to the top.</p>

        <p><b>Q</b> focuses and selects the visible search or filter field on Search, Media, Favorites and Library. It is a quick way to start again.</p>
        <h2>Keyboard shortcuts</h2>
        <p><span class="kbd-key">Q</span> search bar · <span class="kbd-key">D</span>/<span class="kbd-key">↓</span> next · <span class="kbd-key">A</span>/<span class="kbd-key">↑</span> previous · <span class="kbd-key">C</span> context · <span class="kbd-key">S</span> favorite · <span class="kbd-key">F</span> furigana · <span class="kbd-key">?</span> help · <span class="kbd-key">Esc</span> close</p>

        <h2 id="reibun">Anki add-on: Aobana Reibun</h2>
        <!--reibun-->
        <p>Aobana Reibun (例文, "example sentences") is an Anki add-on that fills your cards with Japanese example sentences. With Aobana, it picks a sentence from your own subtitles, books, manga and Custom files, with its furigana, the title it comes from, the lines around it, and for manga the page's image. If Aobana is not running, the add-on starts it and stops it when done.</p>
        <ul>
          <li><b>A whole deck at once</b>: "Tools → Aobana Reibun → Run" fills a deck, and the Browser fills the notes you select. When a field is already filled, you choose to skip it, replace it or add to it.</li>
          <li><b>One card while reviewing</b>: <span class="kbd-key">Ctrl+Shift+W</span> puts an Aobana sentence on the current card.</li>
          <li><b>Two more sources</b>: Nadeshiko (needs an API key) and Immersion Kit (no key) add sentences with a screenshot and audio (<span class="kbd-key">Ctrl+Shift+O</span>, <span class="kbd-key">Ctrl+Shift+K</span>).</li>
          <li><b>Known words for i+1</b>: while Anki is open, Aobana can read your decks' words through the add-on. Press "Import from Anki" under "Known words" in <a href="/?tab=settings">Settings</a>. Nothing in Anki changes.</li>
        </ul>
        <p>To install it, open "Tools → Add-ons" in Anki, press "Get Add-ons..." and enter the code above. It started from AnkiAutoImage's code.</p>

        <h2>Appearance and settings</h2>
        <p>The buttons at the top right show keyboard shortcuts (?), and switch language (日本語 / English) and theme (Paper, Haze, Night, Midnight).</p>

        <h2>Quitting</h2>
        <p>Aobana runs in a window titled "露草 / Aobana" (a Terminal window on macOS and Linux). Close it to quit; closing the browser tab does not stop Aobana.</p>
      `,
    };
    const REIBUN_CODE = '1429349152';
    function reibunTop() {
      if (!REIBUN_CODE) return `<div class="guide-top"><span class="guide-version">Aobana Reibun</span></div>`;
      const code = esc(REIBUN_CODE);
      return `<div class="guide-top"><span class="guide-version">Aobana Reibun</span>` +
        `<code id="reibun-code">${code}</code>` +
        `<button class="btn" onclick="copyReibunCode(this)">${esc(t('reibun_copy'))}</button>` +
        `<a class="btn" href="https://ankiweb.net/shared/info/${code}" target="_blank" rel="noopener">AnkiWeb</a></div>`;
    }
    async function copyReibunCode(btn) {
      try { await navigator.clipboard.writeText(REIBUN_CODE); }
      catch (e) {
        const r = document.createRange(); r.selectNodeContents(document.getElementById('reibun-code'));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e2) {}
        if (!ok) return;
      }
      btn.textContent = t('update_copied');
    }
    function initGuideTab() {
      setTitle(t('tab_guide'));
      document.getElementById('guide-body').innerHTML =
        `<div class="guide-top"><span class="guide-version">Aobana ${esc(APP_VERSION)}</span>` +
        `<button class="btn" onclick="openChangelog()">${esc(t('changelog'))}</button>` +
        `<button class="btn" onclick="openWelcome()">${esc(t('welcome_again'))}</button></div>` +
        GUIDE[LANG].replace('<!--reibun-->', reibunTop());
      guideToc();
      if (location.hash === '#reibun') document.getElementById('reibun').scrollIntoView({ block: 'start' });
    }

    function guideToc() {
      const body = document.getElementById('guide-body');
      const heads = [...body.querySelectorAll('h2')];
      if (heads.length < 2) return;
      heads.forEach((h, i) => { if (!h.id) h.id = 'guide-' + (i + 1); });
      const nav = document.createElement('nav');
      nav.className = 'guide-toc';
      nav.setAttribute('aria-label', t('guide_toc'));
      nav.innerHTML = `<button type="button" class="icon-btn guide-toc-btn" aria-expanded="false" aria-label="${esc(t('guide_toc'))}" title="${esc(t('guide_toc'))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 7h12M6 12h12M6 17h12"/></svg><span>${esc(t('guide_toc'))}</span></button>`
        + `<ol class="guide-toc-list" hidden>${heads.map(h => `<li><a href="#${esc(h.id)}">${esc(h.textContent.trim().replace(/^\d+\.\s*/, ''))}</a></li>`).join('')}</ol>`;
      (body.querySelector('h1') || body).append(nav);
      const button = nav.querySelector('.guide-toc-btn'), list = nav.querySelector('.guide-toc-list');
      const links = [...list.querySelectorAll('a')];
      const mark = () => {
        const line = (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bar-h')) || 0) + 32;
        let at = 0;
        heads.forEach((h, i) => { if (h.getBoundingClientRect().top <= line) at = i; });
        links.forEach((a, i) => a.toggleAttribute('aria-current', i === at));
      };
      button.onclick = () => {
        const open = list.hidden;
        list.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
        if (open) { mark(); list.querySelector('[aria-current]')?.scrollIntoView({ block: 'nearest' }); }
      };
      links.forEach((a, i) => a.onclick = e => {
        e.preventDefault();
        closeGuideToc();
        heads[i].scrollIntoView({ block: 'start' });
      });
      document.addEventListener('click', e => { if (!nav.contains(e.target)) closeGuideToc(); });
      let ticking = false;
      window.addEventListener('scroll', () => {
        if (list.hidden || ticking) return;
        ticking = true;
        requestAnimationFrame(() => { ticking = false; mark(); });
      }, { passive: true });
    }
    function closeGuideToc() {
      const list = document.querySelector('.guide-toc-list');
      if (!list || list.hidden) return false;
      list.hidden = true;
      document.querySelector('.guide-toc-btn').setAttribute('aria-expanded', 'false');
      return true;
    }

