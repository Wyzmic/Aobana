
#ifndef AppVersion
  #error Build with release\build.py, which defines AppVersion, SourceDir and IconFile
#endif

[Setup]
; The AppId is the installation's identity: an upgrade finds the old one by it. Never change it.
AppId={{dedba003-ceb5-4880-a40f-660dc88c9345}
AppName=Aobana
AppVersion={#AppVersion}
AppVerName=Aobana {#AppVersion}
AppPublisher=Wyzmic
AppPublisherURL=https://github.com/Wyzmic/Aobana
AppSupportURL=https://github.com/Wyzmic/Aobana/issues
VersionInfoVersion={#AppVersion}.0.0
UninstallDisplayName=Aobana
UninstallDisplayIcon={app}\Aobana.exe
SetupIconFile={#IconFile}
DefaultDirName={autopf}\Aobana
DisableDirPage=no
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
#define Pics ExtractFilePath(IconFile)
WizardImageFile={#Pics}wizard-panel-202.png,{#Pics}wizard-panel-269.png,{#Pics}wizard-panel-336.png,{#Pics}wizard-panel-403.png,{#Pics}wizard-panel-430.png,{#Pics}wizard-panel-498.png,{#Pics}wizard-panel-534.png
WizardSmallImageFile={#Pics}wizard-small-58.png,{#Pics}wizard-small-71.png,{#Pics}wizard-small-85.png,{#Pics}wizard-small-103.png,{#Pics}wizard-small-112.png,{#Pics}wizard-small-129.png,{#Pics}wizard-small-147.png
ShowLanguageDialog=yes
CloseApplications=yes
RestartApplications=no
Compression=lzma2/ultra64
SolidCompression=yes
OutputBaseFilename=Aobana-Setup-{#AppVersion}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
en.ShortcutName=Aobana
ja.ShortcutName=Aobana
en.MediaCaption=Media folders
ja.MediaCaption=字幕と書籍のフォルダ
en.MediaDescription=Where are your subtitles and books?
ja.MediaDescription=字幕と書籍をどこに置きますか？
en.MediaText=Aobana reads .srt / .ass subtitles and .epub books from these two folders. Keep the suggestions to create two new empty folders, or click Browse to use folders you already have. If you only have one kind, leave the other empty. You can change both later in the Settings tab.%n%nInside the subtitles folder, give each show a folder of its own.
ja.MediaText=Aobana は、この2つのフォルダにある字幕（.srt / .ass）と書籍（.epub）を読み込みます。このままにすると新しい空のフォルダを作ります。すでにあるフォルダを使う場合は「参照」から選んでください。片方しかない場合は、もう一方を空欄にしてください。どちらも後から設定タブで変更できます。%n%n字幕フォルダの中は、作品ごとにフォルダを分けてください。
en.MediaTextExisting=These are the folders Aobana uses now. Keep them, or click Browse to choose others. If you only have one kind, leave the other empty. You can change both later in the Settings tab.%n%nInside the subtitles folder, give each show a folder of its own.
ja.MediaTextExisting=Aobana が現在使っているフォルダです。このままにするか、「参照」から別のフォルダを選んでください。片方しかない場合は、もう一方を空欄にしてください。どちらも後から設定タブで変更できます。%n%n字幕フォルダの中は、作品ごとにフォルダを分けてください。
en.MediaSubs=Subtitles folder:
ja.MediaSubs=字幕フォルダ:
en.MediaBooks=Books folder:
ja.MediaBooks=書籍フォルダ:
en.BrowseSecond=&Browse...
ja.BrowseSecond=参照(&B)...
en.MediaNotFull=Enter a full path, such as C:\Media\Subtitles, or leave the field empty.
ja.MediaNotFull=C:\Media\字幕 のような完全なパスを入力するか、空欄のままにしてください。
en.NotSet=(not set: choose it later in the Settings tab)
ja.NotSet=（未設定: 後から設定タブで指定できます）
en.StartMenuIcon=Create a &Start menu shortcut
ja.StartMenuIcon=スタートメニューにショートカットを作成する(&S)
en.MediaPort=Port (Aobana opens at http://127.0.0.1:<port>/):
ja.MediaPort=ポート（Aobana は http://127.0.0.1:<ポート>/ で開きます）:
en.PortBusy=Port %1 is already used by another program on this computer, so %2 is suggested instead. You can change it later in the Settings tab.
ja.PortBusy=ポート %1 はこのパソコンの別のプログラムが使用しているため、代わりに %2 を候補にしました。後から設定タブで変更できます。
en.PortBad=Enter a port number from 1024 to 65535.
ja.PortBad=ポートには 1024〜65535 の数字を入力してください。
en.PortTaken=Port %1 is already in use by another program. Choose another number, or close that program first.
ja.PortTaken=ポート %1 は別のプログラムが使用しています。別の番号を選ぶか、そのプログラムを先に終了してください。
en.MediaSame=The subtitles folder and the books folder must be two different folders.
ja.MediaSame=字幕フォルダと書籍フォルダには、別々のフォルダを指定してください。
en.FinishedMedia=Subtitles folder: %1%nBooks folder: %2
ja.FinishedMedia=字幕フォルダ: %1%n書籍フォルダ: %2
en.FinishedMediaPerUser=Subtitles and books: each account gets its own Documents\Aobana\Subtitles and Documents\Aobana\Books folders the first time it starts Aobana.
ja.FinishedMediaPerUser=字幕と書籍: 各アカウントの初回起動時に、そのアカウントのドキュメント\Aobana\Subtitles と ドキュメント\Aobana\Books を作ります。
en.FinishedText=Aobana is installed.%n%n%1%nDatabases: %2%nSettings: %4%3
ja.FinishedText=Aobana のインストールが完了しました。%n%n%1%nデータベース: %2%n設定: %4%3
en.DbCaption=Databases
ja.DbCaption=データベースの保存先
en.DbDescription=Where should Aobana keep its databases?
ja.DbDescription=データベースをどこに保存しますか？
en.DbText=Aobana keeps its databases (subs.db, epub.db and manga.db), which hold the index, in this folder. Keep the suggestion, or choose a folder that already holds Aobana databases to use them as they are. Indexing writes here, so the folder must be writable.
ja.DbText=Aobana はインデックスを入れたデータベース（subs.db・epub.db・manga.db）をこのフォルダに保存します。このままでもかまいません。すでに Aobana のデータベースがあるフォルダを選ぶと、それをそのまま使います。インデックス作成はここに書き込むため、書き込めるフォルダを選んでください。
en.DbFound=Found in this folder: %1. Aobana will use these databases.
ja.DbFound=このフォルダにあります: %1。このデータベースを使います。
en.DbNone=No databases in this folder yet: indexing creates them.
ja.DbNone=このフォルダにはまだデータベースがありません。インデックス作成で作られます。
en.DbNotWritable=Aobana could not write to this folder:%n%n%1%n%nIndexing needs to write there. Choose another folder.
ja.DbNotWritable=このフォルダに書き込めませんでした:%n%n%1%n%nインデックス作成で書き込む必要があります。別のフォルダを選んでください。
en.DbDefault=Back to &default
ja.DbDefault=既定の場所に戻す(&D)
en.RunAsAdmin=Run as &administrator
ja.RunAsAdmin=管理者として実行(&A)
en.DirNeedsAdmin=Setup cannot write to this folder without administrator rights:%n%n%1%n%nRestart the setup as administrator (installing for all users)?
ja.DirNeedsAdmin=このフォルダには管理者権限がないと書き込めません:%n%n%1%n%nセットアップを管理者として再起動しますか？（すべてのユーザー用にインストールします）
en.MediaInApp=Chosen in Aobana at its first start: the media you use, and their folders.
ja.MediaInApp=初回起動時に Aobana の中で、使うメディアとそのフォルダを選びます。
en.FinishedSetup=Nothing is indexed yet. Start Aobana and press "Set up Aobana" to choose what you use.
ja.FinishedSetup=まだ何もインデックスされていません。Aobana を起動し、「Aobana を設定する」を押して使うメディアを選んでください。
en.FinishedEmpty=Nothing is indexed yet. Put your files in the folders, then press "Index library" in the Library tab.
ja.FinishedEmpty=まだ何もインデックスされていません。フォルダにファイルを入れてから、ライブラリタブで「インデックス作成」を押してください。
en.FinishedReindex=The folders changed: press "Index library" in the Library tab to index them.
ja.FinishedReindex=フォルダが変わりました。ライブラリタブで「インデックス作成」を押してください。
en.ReadyMedia=Media folders:
en.ReadyDb=Databases:
en.ReadyAddress=Aobana opens at:
en.UninstCaption=Uninstall Aobana
ja.ReadyMedia=字幕と書籍のフォルダ:
ja.ReadyDb=データベースの保存先:
ja.ReadyAddress=Aobana のアドレス:
ja.UninstCaption=Aobana のアンインストール
en.UninstHeading=Choose what to delete along with the program
en.UninstIntro=Anything left unticked stays on this computer, and installing Aobana again picks it up where it was.
ja.UninstHeading=プログラムと一緒に削除するものを選んでください
ja.UninstIntro=チェックしなかったものはこのパソコンに残り、再インストールするとそのまま使われます。
en.UninstSettings=Settings and logs
ja.UninstSettings=設定とログ
en.UninstSettingsNote=%1%nSettings (config.json), logs, and the files kept for updates.
ja.UninstSettingsNote=%1%n設定（config.json）、ログ、アップデートの一時ファイルです。
en.UninstIndex=Databases and caches
ja.UninstIndex=データベースとキャッシュ
en.UninstIndexNote=%1 (%2)%nThe databases (subs.db, epub.db, manga.db), the library check's results, the files left out of the index, and the search cache. Without them, the library has to be indexed again.
ja.UninstIndexNote=%1（%2）%nデータベース（subs.db・epub.db・manga.db）、ライブラリの点検の結果、インデックスしないファイルの一覧、検索キャッシュです。削除すると、インデックス作成をやり直す必要があります。
en.UninstIndexNoteNoDb=%1 (%2)%nThe library check's results, the files left out of the index, and the search cache. There are no databases (subs.db, epub.db, manga.db) here.
ja.UninstIndexNoteNoDb=%1（%2）%nライブラリの点検の結果、インデックスしないファイルの一覧、検索キャッシュです。データベース（subs.db・epub.db・manga.db）はありません。
en.UninstSubs=The subtitles folder and everything in it
ja.UninstSubs=字幕フォルダとその中身すべて
en.UninstBooks=The books folder and everything in it
ja.UninstBooks=書籍フォルダとその中身すべて
en.UninstFolderNote=%1 (%2 files, %3)
ja.UninstFolderNote=%1（%2 ファイル、%3）
en.UninstKept=Always kept, because these are folders you chose, not Aobana's own:
ja.UninstKept=次のものはご自身で選んだフォルダにあるため、削除しません:
en.UninstKeptSubs=Subtitles: %1
ja.UninstKeptSubs=字幕: %1
en.UninstKeptBooks=Books: %1
ja.UninstKeptBooks=書籍: %1
en.UninstKeptIndex=Databases: %1
ja.UninstKeptIndex=データベース: %1
en.UninstBrowser=Favorites and display settings are stored by your browser. Clearing the site data for 127.0.0.1 in the browser removes them.
ja.UninstBrowser=お気に入りと表示設定はブラウザに保存されています。ブラウザで 127.0.0.1 のサイトデータを消去すると削除されます。
en.UninstAll=Tick &all
ja.UninstAll=すべて選択(&A)
en.UninstNext=&Next
ja.UninstNext=次へ(&N)
en.UninstLeft=These could not be deleted. Delete them by hand if you want them gone:%n%n%1
ja.UninstLeft=次のものを削除できませんでした。不要な場合は手動で削除してください:%n%n%1

[Messages]
en.ConfirmUninstall=Remove Aobana now, together with what you ticked?
ja.ConfirmUninstall=Aobana と、チェックした項目を削除します。よろしいですか？

[Tasks]
Name: "startmenuicon"; Description: "{cm:StartMenuIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{autoprograms}\露草 Aobana.lnk"
Type: files; Name: "{autodesktop}\露草 Aobana.lnk"
Type: files; Name: "{app}\Aobana-debug.bat"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\README.ja.md"
Type: files; Name: "{app}\requirements.txt"
Type: files; Name: "{app}\data\ruby\ruby_decisions.tsv"
Type: files; Name: "{app}\data\ruby\ruby_dict_merge.tsv"
Type: files; Name: "{app}\data\ruby\ruby_whole.tsv"
Type: files; Name: "{app}\data\ruby\ruby_trim.tsv"
Type: files; Name: "{app}\data\ruby\gloss_ruby.tsv"
Type: files; Name: "{app}\data\ruby\gloss_names.tsv"
Type: files; Name: "{app}\data\ruby\unclosed_ruby.tsv"
Type: files; Name: "{app}\data\ruby\ass_pairs.tsv"
Type: files; Name: "{app}\app.py"
Type: files; Name: "{app}\engine.py"
Type: files; Name: "{app}\utils.py"
Type: files; Name: "{app}\paths.py"
Type: files; Name: "{app}\library.py"
Type: files; Name: "{app}\analyser.py"
Type: files; Name: "{app}\indexer.py"
Type: files; Name: "{app}\epub_indexer.py"
Type: files; Name: "{app}\manga_indexer.py"
Type: files; Name: "{app}\ass_ruby.py"
Type: files; Name: "{app}\folder_picker.py"
Type: files; Name: "{app}\updater.py"
Type: files; Name: "{app}\launcher.py"
Type: files; Name: "{app}\index.html"
Type: filesandordirs; Name: "{app}\__pycache__"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{cm:ShortcutName}"; Filename: "{app}\Aobana.exe"; WorkingDir: "{app}"; Tasks: startmenuicon
Name: "{autodesktop}\{cm:ShortcutName}"; Filename: "{app}\Aobana.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Aobana.exe"; Description: "{cm:LaunchProgram,Aobana}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\aobana.installed"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\aobana\__pycache__"
Type: filesandordirs; Name: "{app}\aobana\server\__pycache__"
Type: filesandordirs; Name: "{app}\aobana\search\__pycache__"
Type: filesandordirs; Name: "{app}\aobana\indexing\__pycache__"

[Code]
var
  MediaPage: TInputQueryWizardPage;
  BrowseButtons: array[0..1] of TNewButton;
  PortNote: TNewStaticText;
  PortChecked: Boolean;
  DbPage: TInputDirWizardPage;
  DbNote: TNewStaticText;
  DbDefaultButton: TNewButton;
  AdminButton: TNewButton;
  Relaunching: Boolean;
  TaskBoxes: array[0..1] of TNewCheckBox;
  Prefill: array[0..3] of String;
  PrefillDir: String;
  FromExisting: Boolean;
  WasUpgrade: Boolean;
  OldMarker: String;

function MarkerPath(): String;
begin
  Result := ExpandConstant('{app}\aobana.installed');
end;

function DefaultMedia(Name: String): String;
begin
  Result := ExpandConstant('{userdocs}\Aobana\') + Name;
end;

function SameFolder(A, B: String): Boolean;
begin
  Result := CompareText(RemoveBackslashUnlessRoot(Trim(A)), RemoveBackslashUnlessRoot(Trim(B))) = 0;
end;

function IsDefaultMedia(Path: String; Index: Integer): Boolean;
begin
  if Index = 0 then
    Result := SameFolder(Path, DefaultMedia('Subtitles'))
  else
    Result := SameFolder(Path, DefaultMedia('Books'));
end;

function KeptDefaults(): Boolean;
begin
  Result := IsDefaultMedia(MediaPage.Values[0], 0) and IsDefaultMedia(MediaPage.Values[1], 1);
end;

function FoldersChanged(): Boolean;
begin
  Result := not SameFolder(MediaPage.Values[0], Prefill[0]) or
            not SameFolder(MediaPage.Values[1], Prefill[1]);
end;

function DefaultDb(): String;
begin
  Result := ExpandConstant('{localappdata}\Aobana\db');
end;

function DbChanged(): Boolean;
begin
  Result := not SameFolder(DbPage.Values[0], Prefill[3]);
end;

function CanWrite(Dir: String): Boolean;
var
  Probe: String;
begin
  Dir := RemoveBackslashUnlessRoot(Trim(Dir));
  while (Dir <> '') and not DirExists(Dir) and (ExtractFileDir(Dir) <> Dir) do
    Dir := ExtractFileDir(Dir);
  Probe := AddBackslash(Dir) + 'aobana-write-test.tmp';
  Result := SaveStringToFile(Probe, '', False);
  if Result then
    DeleteFile(Probe);
end;

function ShellExecuteW(Wnd: HWND; Verb, FileName, Params, Dir: String; Show: Integer): Integer;
  external 'ShellExecuteW@shell32.dll stdcall';

procedure RelaunchAsAdmin();
begin
  if ShellExecuteW(WizardForm.Handle, 'runas', ExpandConstant('{srcexe}'),
                   '/ALLUSERS /LANG=' + ActiveLanguage() + ' /DIR="' + WizardDirValue() + '"',
                   '', SW_SHOWNORMAL) > 32 then
  begin
    Relaunching := True;
    WizardForm.Close;
  end;
end;

const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{dedba003-ceb5-4880-a40f-660dc88c9345}_is1';

function PerUserInstalled(): Boolean;
begin
  Result := RegKeyExists(HKCU, UninstallKey) and
            not RegKeyExists(HKLM64, UninstallKey) and not RegKeyExists(HKLM32, UninstallKey);
end;

function HasParam(Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount() do
    if CompareText(ParamStr(I), Name) = 0 then
      Result := True;
end;

function InitializeSetup(): Boolean;
var
  Params: String;
  I: Integer;
begin
  Result := True;
  if not IsAdminInstallMode() or HasParam('/ALLUSERS') or HasParam('/CURRENTUSER') or not PerUserInstalled() then
    Exit;
  Params := '/CURRENTUSER';
  for I := 1 to ParamCount() do
    Params := Params + ' "' + ParamStr(I) + '"';
  if ShellExecuteW(0, 'open', ExpandConstant('{srcexe}'), Params, '', SW_SHOWNORMAL) > 32 then
    Result := False;
end;

procedure AdminClick(Sender: TObject);
begin
  RelaunchAsAdmin();
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if Relaunching then
    Confirm := False;
end;

procedure ShowDbNote(Sender: TObject);
var
  Dir, Found: String;
begin
  Dir := AddBackslash(Trim(DbPage.Values[0]));
  Found := '';
  if FileExists(Dir + 'subs.db') then
    Found := 'subs.db';
  if FileExists(Dir + 'epub.db') then
  begin
    if Found <> '' then
      Found := Found + ', ';
    Found := Found + 'epub.db';
  end;
  if FileExists(Dir + 'manga.db') then
  begin
    if Found <> '' then
      Found := Found + ', ';
    Found := Found + 'manga.db';
  end;
  if Found <> '' then
    DbNote.Caption := FmtMessage(CustomMessage('DbFound'), [Found])
  else
    DbNote.Caption := CustomMessage('DbNone');
end;

procedure DbDefaultClick(Sender: TObject);
begin
  DbPage.Values[0] := DefaultDb();
  ShowDbNote(nil);
end;

function JsonString(S: String): String;
begin
  StringChangeEx(S, '\', '\\', True);
  StringChangeEx(S, '"', '\"', True);
  Result := '"' + S + '"';
end;

function ReadText(FileName: String): String;
var
  Raw: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(FileName, Raw) then
    Result := Utf8Decode(Raw);
end;

function JsonField(Text, Key: String; var Value: String; var IsStr: Boolean): Boolean;
var
  P: Integer;
  C: String;
begin
  Result := False;
  Value := '';
  IsStr := False;
  P := Pos('"' + Key + '"', Text);
  if P = 0 then
    Exit;
  P := P + Length(Key) + 2;
  while (P <= Length(Text)) and ((Text[P] = ' ') or (Text[P] = #9) or (Text[P] = #13) or (Text[P] = #10) or (Text[P] = ':')) do
    P := P + 1;
  if P > Length(Text) then
    Exit;
  if Text[P] = '"' then
  begin
    IsStr := True;
    P := P + 1;
    while (P <= Length(Text)) and (Text[P] <> '"') do
    begin
      C := Text[P];
      if (C = '\') and (P < Length(Text)) then
      begin
        P := P + 1;
        C := Text[P];
        if C = 'n' then C := #10
        else if C = 't' then C := #9
        else if C = 'r' then C := #13
        else if (C = 'u') and (P + 4 <= Length(Text)) then
        begin
          C := Chr(StrToIntDef('$' + Copy(Text, P + 1, 4), 63));
          P := P + 4;
        end;
      end;
      Value := Value + C;
      P := P + 1;
    end;
    Result := P <= Length(Text);
  end
  else
  begin
    while (P <= Length(Text)) and (((Text[P] >= '0') and (Text[P] <= '9')) or (Text[P] = '-')) do
    begin
      Value := Value + Text[P];
      P := P + 1;
    end;
    Result := Value <> '';
  end;
end;

function ReadFolders(Text: String; var Subs, Books: String): Boolean;
var
  IsStr: Boolean;
begin
  Result := False;
  if JsonField(Text, 'subs_dir', Subs, IsStr) then Result := True else Subs := '';
  if JsonField(Text, 'books_dir', Books, IsStr) then Result := True else Books := '';
end;

function WritesFolders(): Boolean;
begin
  Result := FromExisting or (ExpandConstant('{param:SUBSDIR}') <> '') or (ExpandConstant('{param:BOOKSDIR}') <> '');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = MediaPage.ID) or (PageID = DbPage.ID);
end;

function FoldersPerAccount(): Boolean;
var
  S, B: String;
begin
  if WasUpgrade then
    Result := IsAdminInstallMode() and not FoldersChanged() and not ReadFolders(OldMarker, S, B)
  else
    Result := IsAdminInstallMode() and KeptDefaults();
end;

procedure BrowseClick(Sender: TObject);
var
  I: Integer;
  Dir: String;
begin
  for I := 0 to 1 do
    if Sender = BrowseButtons[I] then
    begin
      Dir := MediaPage.Values[I];
      if BrowseForFolder(SetupMessage(msgBrowseDialogLabel), Dir, True) then
        MediaPage.Values[I] := Dir;
    end;
end;

function PortBusy(Port: Integer): Boolean;
var
  Tmp, P, L: String;
  Lines: TArrayOfString;
  I, Code: Integer;
begin
  Result := False;
  Tmp := ExpandConstant('{tmp}\netstat.txt');
  if not Exec(ExpandConstant('{cmd}'), '/C netstat -an > "' + Tmp + '"', '', SW_HIDE,
              ewWaitUntilTerminated, Code) then
    Exit;
  if not LoadStringsFromFile(Tmp, Lines) then
    Exit;
  P := ':' + IntToStr(Port) + ' ';
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    L := Lines[I];
    if (Pos('TCP', L) > 0) and (Pos(P, L) > 0) and
       ((Pos(' 0.0.0.0:0 ', L) > 0) or (Pos(' [::]:0 ', L) > 0)) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function PortValue(): Integer;
begin
  Result := StrToIntDef(Trim(MediaPage.Values[2]), 0);
end;

function FullPathOrBlank(S: String): Boolean;
begin
  S := Trim(S);
  Result := (S = '') or ((Length(S) >= 3) and (Copy(S, 2, 2) = ':\')) or (Copy(S, 1, 2) = '\\');
end;

function TaskIndex(I: Integer): Integer;
var
  J: Integer;
  Caption: String;
begin
  Result := -1;
  if I = 0 then
    Caption := CustomMessage('StartMenuIcon')
  else
    Caption := CustomMessage('CreateDesktopIcon');
  for J := 0 to WizardForm.TasksList.Items.Count - 1 do
    if WizardForm.TasksList.ItemCaption[J] = Caption then
      Result := J;
end;

procedure TaskBoxClick(Sender: TObject);
var
  I, J: Integer;
begin
  for I := 0 to 1 do
    if Sender = TaskBoxes[I] then
    begin
      J := TaskIndex(I);
      if J >= 0 then
        WizardForm.TasksList.Checked[J] := TaskBoxes[I].Checked;
    end;
end;

procedure MakeTaskBoxes();
var
  Group: TNewStaticText;
  I, Top: Integer;
begin
  Group := TNewStaticText.Create(WizardForm);
  Group.Parent := WizardForm.TasksList.Parent;
  Group.Left := WizardForm.TasksList.Left;
  Group.Top := WizardForm.TasksList.Top;
  Group.Caption := CustomMessage('AdditionalIcons');
  Top := Group.Top + Group.Height + ScaleY(8);
  for I := 0 to 1 do
  begin
    TaskBoxes[I] := TNewCheckBox.Create(WizardForm);
    TaskBoxes[I].Parent := WizardForm.TasksList.Parent;
    TaskBoxes[I].Left := WizardForm.TasksList.Left + ScaleX(4);
    TaskBoxes[I].Top := Top;
    TaskBoxes[I].Width := WizardForm.TasksList.Width - ScaleX(4);
    TaskBoxes[I].Height := ScaleY(20);
    TaskBoxes[I].OnClick := @TaskBoxClick;
    Top := Top + ScaleY(26);
  end;
  TaskBoxes[0].Caption := CustomMessage('StartMenuIcon');
  TaskBoxes[1].Caption := CustomMessage('CreateDesktopIcon');
  WizardForm.TasksList.Visible := False;
end;

procedure TaskBoxesShow();
var
  I, J: Integer;
begin
  for I := 0 to 1 do
  begin
    J := TaskIndex(I);
    TaskBoxes[I].Visible := J >= 0;
    if J >= 0 then
      TaskBoxes[I].Checked := WizardForm.TasksList.Checked[J];
  end;
end;

procedure InitializeWizard();
var
  I: Integer;
begin
  MediaPage := CreateInputQueryPage(wpSelectDir, CustomMessage('MediaCaption'),
    CustomMessage('MediaDescription'), CustomMessage('MediaText'));
  MediaPage.Add(CustomMessage('MediaSubs'), False);
  MediaPage.Add(CustomMessage('MediaBooks'), False);
  MediaPage.Add(CustomMessage('MediaPort'), False);
  MediaPage.Edits[2].Width := ScaleX(80);
  MediaPage.Values[2] := ExpandConstant('{param:PORT|5000}');
  PortNote := TNewStaticText.Create(MediaPage);
  PortNote.Parent := MediaPage.Surface;
  PortNote.Left := MediaPage.Edits[2].Left + MediaPage.Edits[2].Width + ScaleX(10);
  PortNote.Top := MediaPage.Edits[2].Top;
  PortNote.Width := MediaPage.SurfaceWidth - PortNote.Left;
  PortNote.AutoSize := False;
  PortNote.WordWrap := True;
  PortNote.Height := ScaleY(40);
  PortNote.Caption := '';
  for I := 0 to 1 do
  begin
    BrowseButtons[I] := TNewButton.Create(MediaPage);
    BrowseButtons[I].Parent := MediaPage.Surface;
    BrowseButtons[I].Width := ScaleX(80);
    BrowseButtons[I].Height := WizardForm.NextButton.Height;
    BrowseButtons[I].Left := MediaPage.SurfaceWidth - BrowseButtons[I].Width;
    MediaPage.Edits[I].Width := BrowseButtons[I].Left - ScaleX(10) - MediaPage.Edits[I].Left;
    BrowseButtons[I].Top := MediaPage.Edits[I].Top + (MediaPage.Edits[I].Height - BrowseButtons[I].Height) div 2;
    BrowseButtons[I].OnClick := @BrowseClick;
  end;
  BrowseButtons[0].Caption := SetupMessage(msgButtonWizardBrowse);
  BrowseButtons[1].Caption := CustomMessage('BrowseSecond');
  DbPage := CreateInputDirPage(MediaPage.ID, CustomMessage('DbCaption'), CustomMessage('DbDescription'),
    CustomMessage('DbText'), False, 'Aobana');
  DbPage.Add('');
  DbPage.Edits[0].OnChange := @ShowDbNote;
  DbDefaultButton := TNewButton.Create(DbPage);
  DbDefaultButton.Parent := DbPage.Surface;
  DbDefaultButton.Caption := CustomMessage('DbDefault');
  DbDefaultButton.Left := DbPage.Edits[0].Left;
  DbDefaultButton.Top := DbPage.Edits[0].Top + DbPage.Edits[0].Height + ScaleY(8);
  DbDefaultButton.Height := WizardForm.NextButton.Height;
  DbDefaultButton.Width := ScaleX(150);
  DbDefaultButton.OnClick := @DbDefaultClick;
  DbNote := TNewStaticText.Create(DbPage);
  DbNote.Parent := DbPage.Surface;
  DbNote.Left := DbPage.Edits[0].Left;
  DbNote.Top := DbDefaultButton.Top + DbDefaultButton.Height + ScaleY(10);
  DbNote.Width := DbPage.SurfaceWidth - DbNote.Left;
  DbNote.AutoSize := False;
  DbNote.WordWrap := True;
  DbNote.Height := ScaleY(40);
  AdminButton := TNewButton.Create(WizardForm);
  AdminButton.Parent := WizardForm;
  AdminButton.Caption := CustomMessage('RunAsAdmin');
  AdminButton.Top := WizardForm.CancelButton.Top;
  AdminButton.Height := WizardForm.CancelButton.Height;
  AdminButton.Left := ScaleX(10);
  AdminButton.Width := ScaleX(170);
  AdminButton.OnClick := @AdminClick;
  AdminButton.Visible := False;
  MakeTaskBoxes();
end;

function ParamFolder(Name, Current: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '}');
  if Result = '' then
    Result := Current
  else if Result = '-' then
    Result := '';
end;

procedure DoPrefill();
var
  Cfg, S, B, P, D: String;
  IsStr: Boolean;
begin
  if (PrefillDir <> '') and SameFolder(PrefillDir, WizardDirValue()) then
    Exit;
  PrefillDir := WizardDirValue();
  WasUpgrade := FileExists(MarkerPath());
  OldMarker := ReadText(MarkerPath());
  Cfg := ReadText(ExpandConstant('{localappdata}\Aobana\config.json'));
  FromExisting := ReadFolders(Cfg, S, B);
  if not FromExisting then
    FromExisting := ReadFolders(OldMarker, S, B);
  if not FromExisting then
  begin
    S := DefaultMedia('Subtitles');
    B := DefaultMedia('Books');
  end;
  if not (JsonField(Cfg, 'port', P, IsStr) and not IsStr) then
    if not (JsonField(OldMarker, 'port', P, IsStr) and not IsStr) then
      P := '5000';
  if not (JsonField(Cfg, 'db_dir', D, IsStr) and IsStr and (D <> '')) then
    if not (JsonField(OldMarker, 'db_dir', D, IsStr) and IsStr and (D <> '')) then
      D := DefaultDb();
  Prefill[0] := S;
  Prefill[1] := B;
  Prefill[2] := P;
  Prefill[3] := D;
  MediaPage.Values[0] := ParamFolder('SUBSDIR', S);
  MediaPage.Values[1] := ParamFolder('BOOKSDIR', B);
  MediaPage.Values[2] := ExpandConstant('{param:PORT|' + P + '}');
  DbPage.Values[0] := ExpandConstant('{param:DBDIR}');
  if DbPage.Values[0] = '' then
    DbPage.Values[0] := D;
  PortChecked := False;
  PortNote.Caption := '';
  if FromExisting then
    MediaPage.SubCaptionLabel.Caption := CustomMessage('MediaTextExisting')
  else
    MediaPage.SubCaptionLabel.Caption := CustomMessage('MediaText');
  Log('Media page from ' + PrefillDir + ': upgrade=' + IntToStr(Ord(WasUpgrade)) +
      ' existing=' + IntToStr(Ord(FromExisting)) + ' subs=' + Prefill[0] + ' books=' + Prefill[1] +
      ' port=' + Prefill[2] + ' db=' + Prefill[3]);
end;

function KeepsOwnPort(): Boolean;
begin
  Result := WasUpgrade and (PortValue() = StrToIntDef(Prefill[2], 0));
end;

procedure CheckPort();
var
  Port, Free: Integer;
begin
  if PortChecked then
    Exit;
  PortChecked := True;
  if KeepsOwnPort() then
    Exit;
  Port := PortValue();
  if (Port < 1024) or (Port > 65535) or not PortBusy(Port) then
    Exit;
  Free := Port + 1;
  while (Free <= 65535) and (Free < Port + 50) and PortBusy(Free) do
    Free := Free + 1;
  if Free > 65535 then
    Exit;
  MediaPage.Values[2] := IntToStr(Free);
  PortNote.Caption := FmtMessage(CustomMessage('PortBusy'), [IntToStr(Port), IntToStr(Free)]);
  Log('Port ' + IntToStr(Port) + ' is in use; suggested ' + IntToStr(Free));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if not IsAdminInstallMode() and not WizardSilent() and not CanWrite(WizardDirValue()) then
    begin
      if MsgBox(FmtMessage(CustomMessage('DirNeedsAdmin'), [WizardDirValue()]), mbConfirmation, MB_YESNO) = IDYES then
        RelaunchAsAdmin();
      Result := False;
      Exit;
    end;
    DoPrefill();
  end;
  if CurPageID = DbPage.ID then
  begin
    DbPage.Values[0] := RemoveBackslashUnlessRoot(Trim(DbPage.Values[0]));
    if not WizardSilent() and not CanWrite(DbPage.Values[0]) then
    begin
      MsgBox(FmtMessage(CustomMessage('DbNotWritable'), [DbPage.Values[0]]), mbError, MB_OK);
      Result := False;
    end;
    Exit;
  end;
  if CurPageID <> MediaPage.ID then
    Exit;
  DoPrefill();
  CheckPort();
  if (PortValue() < 1024) or (PortValue() > 65535) then
  begin
    MsgBox(CustomMessage('PortBad'), mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if (not WizardSilent()) and (PortNote.Caption = '') and not KeepsOwnPort() and PortBusy(PortValue()) then
  begin
    MsgBox(FmtMessage(CustomMessage('PortTaken'), [IntToStr(PortValue())]), mbError, MB_OK);
    Result := False;
    Exit;
  end;
  for I := 0 to 1 do
  begin
    MediaPage.Values[I] := Trim(MediaPage.Values[I]);
    if not FullPathOrBlank(MediaPage.Values[I]) then
    begin
      MsgBox(CustomMessage('MediaNotFull'), mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
  if (MediaPage.Values[0] <> '') and
     (CompareText(RemoveBackslashUnlessRoot(MediaPage.Values[0]),
                  RemoveBackslashUnlessRoot(MediaPage.Values[1])) = 0) then
  begin
    MsgBox(CustomMessage('MediaSame'), mbError, MB_OK);
    Result := False;
  end;
end;

function Shown(Folder: String): String;
begin
  if Folder = '' then
    Result := CustomMessage('NotSet')
  else
    Result := Folder;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine + CustomMessage('ReadyMedia') + NewLine;
  if not WritesFolders() then
    Result := Result + Space + CustomMessage('MediaInApp') + NewLine
  else if FoldersPerAccount() then
    Result := Result + Space + CustomMessage('FinishedMediaPerUser') + NewLine
  else
    Result := Result + Space + CustomMessage('MediaSubs') + ' ' + Shown(Trim(MediaPage.Values[0])) + NewLine +
              Space + CustomMessage('MediaBooks') + ' ' + Shown(Trim(MediaPage.Values[1])) + NewLine;
  Result := Result + NewLine + CustomMessage('ReadyDb') + NewLine + Space + Trim(DbPage.Values[0]) + NewLine +
            NewLine + CustomMessage('ReadyAddress') + NewLine + Space +
            'http://127.0.0.1:' + IntToStr(PortValue()) + '/';
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
begin
  if CurStep <> ssPostInstall then
    Exit;
  DoPrefill();
  CheckPort();
  if WasUpgrade and not FoldersChanged() and not DbChanged() and (PortValue() = StrToIntDef(Prefill[2], 0)) then
    Exit;
  SetArrayLength(Lines, 1);
  Lines[0] := '{"installed_at": ' + JsonString(GetDateTimeString('yyyy-mm-dd"T"hh:nn:ss', '-', ':'));
  if WritesFolders() and not FoldersPerAccount() then
  begin
    if MediaPage.Values[0] <> '' then
      ForceDirectories(MediaPage.Values[0]);
    if MediaPage.Values[1] <> '' then
      ForceDirectories(MediaPage.Values[1]);
    Lines[0] := Lines[0] + ', "subs_dir": ' + JsonString(RemoveBackslashUnlessRoot(MediaPage.Values[0])) +
                ', "books_dir": ' + JsonString(RemoveBackslashUnlessRoot(MediaPage.Values[1]));
  end;
  if SameFolder(DbPage.Values[0], DefaultDb()) then
    Lines[0] := Lines[0] + ', "db_dir": ""'
  else
  begin
    ForceDirectories(DbPage.Values[0]);
    Lines[0] := Lines[0] + ', "db_dir": ' + JsonString(RemoveBackslashUnlessRoot(DbPage.Values[0]));
  end;
  Lines[0] := Lines[0] + ', "port": ' + IntToStr(PortValue()) + '}';
  SaveStringsToUTF8File(MarkerPath(), Lines, False);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Media, Data, Tail: String;
  Delta: Integer;
begin
  AdminButton.Visible := not IsAdminInstallMode() and not PerUserInstalled() and
    ((CurPageID = wpSelectDir) or (CurPageID = MediaPage.ID) or (CurPageID = DbPage.ID) or
     (CurPageID = wpSelectTasks) or (CurPageID = wpReady));
  if CurPageID = wpSelectTasks then
    TaskBoxesShow();
  if CurPageID = MediaPage.ID then
    CheckPort();
  if CurPageID = DbPage.ID then
    ShowDbNote(nil);
  if CurPageID <> wpFinished then
    Exit;
  if not WritesFolders() then
    Media := CustomMessage('MediaInApp') + #13#10
  else if FoldersPerAccount() then
    Media := CustomMessage('FinishedMediaPerUser') + #13#10
  else
    Media := FmtMessage(CustomMessage('FinishedMedia'), [Shown(MediaPage.Values[0]), Shown(MediaPage.Values[1])]) + #13#10;
  Data := RemoveBackslashUnlessRoot(DbPage.Values[0]);
  Tail := '';
  if not WritesFolders() then
    Tail := #13#10#13#10 + CustomMessage('FinishedSetup')
  else if not FileExists(Data + '\subs.db') and not FileExists(Data + '\epub.db') and not FileExists(Data + '\manga.db') then
    Tail := #13#10#13#10 + CustomMessage('FinishedEmpty')
  else if FromExisting and FoldersChanged() then
    Tail := #13#10#13#10 + CustomMessage('FinishedReindex');
  Delta := WizardForm.FinishedLabel.Height;
  WizardForm.FinishedLabel.Caption := FmtMessage(CustomMessage('FinishedText'), [Media, Data, Tail, DefaultDb()]);
  WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
  Delta := WizardForm.FinishedLabel.Height - Delta;
  WizardForm.RunList.Top := WizardForm.RunList.Top + Delta;
end;


const
  ATTR_DIR = $10;
  ATTR_REPARSE = $400;

var
  UStore, UDb, USubs, UBooks: String;
  UOffer: array[0..3] of Boolean;
  UChosen: array[0..3] of Boolean;
  UBoxes: array[0..3] of TNewCheckBox;

procedure DirStats(Dir: String; var Files: Integer; var Bytes: Int64);
var
  FR: TFindRec;
begin
  if not FindFirst(AddBackslash(Dir) + '*', FR) then
    Exit;
  try
    repeat
      if (FR.Name <> '.') and (FR.Name <> '..') then
      begin
        if (FR.Attributes and ATTR_DIR) <> 0 then
        begin
          if (FR.Attributes and ATTR_REPARSE) = 0 then
            DirStats(AddBackslash(Dir) + FR.Name, Files, Bytes);
        end
        else
        begin
          Files := Files + 1;
          Bytes := Bytes + Int64(FR.SizeLow) + Int64(FR.SizeHigh) * 4294967296;
        end;
      end;
    until not FindNext(FR);
  finally
    FindClose(FR);
  end;
end;

function SizeText(Bytes: Int64): String;
var
  KB: Integer;
begin
  KB := Bytes div 1024;
  if KB >= 1048576 then
    Result := Format('%d.%.2d GB', [KB div 1048576, (KB mod 1048576) * 100 div 1048576])
  else if KB >= 1024 then
    Result := Format('%d MB', [KB div 1024])
  else
    Result := Format('%d KB', [KB]);
end;

function HasIndex(Dir: String): Boolean;
begin
  Result := (Dir <> '') and (FileExists(AddBackslash(Dir) + 'subs.db') or FileExists(AddBackslash(Dir) + 'epub.db')
             or FileExists(AddBackslash(Dir) + 'manga.db'));
end;

function OwnDb(): Boolean;
begin
  Result := SameFolder(UDb, UStore + '\db');
end;

function IsEmptyDir(Dir: String): Boolean;
var
  Files: Integer;
  Bytes: Int64;
begin
  Files := 0;
  Bytes := 0;
  DirStats(Dir, Files, Bytes);
  Result := Files = 0;
end;

function DbBytes(): Int64;
var
  Files: Integer;
begin
  Files := 0;
  Result := 0;
  DirStats(UDb, Files, Result);
end;

function StoreHasSettings(): Boolean;
var
  FR: TFindRec;
  Own: Boolean;
begin
  Result := False;
  if not FindFirst(UStore + '\*', FR) then
    Exit;
  try
    repeat
      Own := (FR.Name = '.') or (FR.Name = '..') or (CompareText(FR.Name, 'db') = 0);
      if not Own then
        Result := True;
    until Result or not FindNext(FR);
  finally
    FindClose(FR);
  end;
end;

procedure LocateData();
var
  Cfg, Marker, S, B: String;
  IsStr: Boolean;
begin
  UStore := ExpandConstant('{localappdata}\Aobana');
  Cfg := ReadText(UStore + '\config.json');
  Marker := ReadText(MarkerPath());
  if not (JsonField(Cfg, 'db_dir', UDb, IsStr) and IsStr and (UDb <> '')) then
    if not (JsonField(Marker, 'db_dir', UDb, IsStr) and IsStr and (UDb <> '')) then
      UDb := UStore + '\db';
  if not ReadFolders(Cfg, S, B) then
    if not ReadFolders(Marker, S, B) then
    begin
      S := DefaultMedia('Subtitles');
      B := DefaultMedia('Books');
    end;
  USubs := RemoveBackslashUnlessRoot(Trim(S));
  UBooks := RemoveBackslashUnlessRoot(Trim(B));
  UOffer[0] := StoreHasSettings();
  UOffer[1] := OwnDb() and not IsEmptyDir(UDb);
  UOffer[2] := IsDefaultMedia(USubs, 0) and DirExists(USubs);
  UOffer[3] := IsDefaultMedia(UBooks, 1) and DirExists(UBooks);
  Log('Uninstall data: store=' + UStore + ' db=' + UDb + ' subs=' + USubs + ' books=' + UBooks);
end;

procedure TickAllClick(Sender: TObject);
var
  I: Integer;
begin
  for I := 0 to 3 do
    if UOffer[I] then
      UBoxes[I].Checked := True;
end;

function AddLabel(Form: TSetupForm; Top, Left: Integer; S: String; Gray, Bold: Boolean; Gap: Integer): Integer;
var
  Text: TNewStaticText;
begin
  Text := TNewStaticText.Create(Form);
  Text.Parent := Form;
  Text.Left := Left;
  Text.Top := Top;
  Text.Width := Form.ClientWidth - Left - ScaleX(24);
  Text.AutoSize := False;
  Text.WordWrap := True;
  if Gray then
    Text.Font.Color := clGrayText;
  if Bold then
    Text.Font.Style := [fsBold];
  Text.Caption := S;
  Text.AdjustHeight();
  Result := Text.Top + Text.Height + Gap;
end;

function AddChoice(Form: TSetupForm; I, Top: Integer; Caption, Note: String; Checked: Boolean): Integer;
begin
  UBoxes[I] := TNewCheckBox.Create(Form);
  UBoxes[I].Parent := Form;
  UBoxes[I].Left := ScaleX(24);
  UBoxes[I].Top := Top;
  UBoxes[I].Width := Form.ClientWidth - ScaleX(48);
  UBoxes[I].Height := ScaleY(20);
  UBoxes[I].Caption := Caption;
  UBoxes[I].Checked := Checked;
  Result := AddLabel(Form, Top + ScaleY(21), ScaleX(44), Note, True, False, ScaleY(12));
end;

function FolderNote(Dir: String): String;
var
  Files: Integer;
  Bytes: Int64;
begin
  Files := 0;
  Bytes := 0;
  DirStats(Dir, Files, Bytes);
  Result := FmtMessage(CustomMessage('UninstFolderNote'), [Dir, IntToStr(Files), SizeText(Bytes)]);
end;

function ChooseRemovals(): Boolean;
var
  Form: TSetupForm;
  Top, I, W: Integer;
  Kept, Note: String;
  Line: TBevel;
  AllButton, NextButton, CancelButton: TNewButton;
begin
  Form := CreateCustomForm(ScaleX(560), ScaleY(400), False, False);
  try
    Form.Caption := CustomMessage('UninstCaption');
    Top := AddLabel(Form, ScaleY(18), ScaleX(24), CustomMessage('UninstHeading'), False, True, ScaleY(6));
    Top := AddLabel(Form, Top, ScaleX(24), CustomMessage('UninstIntro'), False, False, ScaleY(16));
    if UOffer[0] then
      Top := AddChoice(Form, 0, Top, CustomMessage('UninstSettings'),
        FmtMessage(CustomMessage('UninstSettingsNote'), [UStore]), False);
    if UOffer[1] then
    begin
      if HasIndex(UDb) then
        Note := CustomMessage('UninstIndexNote')
      else
        Note := CustomMessage('UninstIndexNoteNoDb');
      Top := AddChoice(Form, 1, Top, CustomMessage('UninstIndex'), FmtMessage(Note, [UDb, SizeText(DbBytes())]), False);
    end;
    if UOffer[2] then
      Top := AddChoice(Form, 2, Top, CustomMessage('UninstSubs'), FolderNote(USubs), False);
    if UOffer[3] then
      Top := AddChoice(Form, 3, Top, CustomMessage('UninstBooks'), FolderNote(UBooks), False);
    Kept := '';
    if (USubs <> '') and not UOffer[2] and DirExists(USubs) then
      Kept := Kept + #13#10 + FmtMessage(CustomMessage('UninstKeptSubs'), [USubs]);
    if (UBooks <> '') and not UOffer[3] and DirExists(UBooks) then
      Kept := Kept + #13#10 + FmtMessage(CustomMessage('UninstKeptBooks'), [UBooks]);
    if not OwnDb() and HasIndex(UDb) then
      Kept := Kept + #13#10 + FmtMessage(CustomMessage('UninstKeptIndex'), [UDb]);
    if Kept <> '' then
    begin
      Top := Top + ScaleY(4);
      Top := AddLabel(Form, Top, ScaleX(24), CustomMessage('UninstKept'), False, False, ScaleY(2));
      Top := AddLabel(Form, Top, ScaleX(44), Copy(Kept, 3, Length(Kept)), True, False, ScaleY(12));
    end;
    Top := AddLabel(Form, Top, ScaleX(24), CustomMessage('UninstBrowser'), True, False, ScaleY(14));

    Line := TBevel.Create(Form);
    Line.Parent := Form;
    Line.Shape := bsTopLine;
    Line.SetBounds(0, Top, Form.ClientWidth, ScaleY(2));
    Top := Top + ScaleY(12);

    AllButton := TNewButton.Create(Form);
    AllButton.Parent := Form;
    AllButton.Caption := CustomMessage('UninstAll');
    AllButton.OnClick := @TickAllClick;
    NextButton := TNewButton.Create(Form);
    NextButton.Parent := Form;
    NextButton.Caption := CustomMessage('UninstNext');
    NextButton.ModalResult := mrOk;
    NextButton.Default := True;
    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := SetupMessage(msgButtonCancel);
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    W := Form.CalculateButtonWidth([AllButton.Caption, NextButton.Caption, CancelButton.Caption]);
    Form.ClientHeight := Top + ScaleY(23 + 12);
    AllButton.SetBounds(ScaleX(24), Top, W, ScaleY(23));
    AllButton.Visible := UOffer[0] or UOffer[1] or UOffer[2] or UOffer[3];
    CancelButton.SetBounds(Form.ClientWidth - ScaleX(24) - W, Top, W, ScaleY(23));
    NextButton.SetBounds(CancelButton.Left - ScaleX(8) - W, Top, W, ScaleY(23));
    Form.ActiveControl := NextButton;
    Form.Position := poScreenCenter;
    Result := Form.ShowModal() = mrOk;
    if Result then
      for I := 0 to 3 do
        UChosen[I] := UOffer[I] and UBoxes[I].Checked;
  finally
    Form.Free();
  end;
end;

procedure ChooseFromParam();
var
  P: String;
  I: Integer;
begin
  P := ',' + Lowercase(ExpandConstant('{param:REMOVE}')) + ',';
  UChosen[0] := (Pos(',all,', P) > 0) or (Pos(',settings,', P) > 0);
  UChosen[1] := (Pos(',all,', P) > 0) or (Pos(',index,', P) > 0);
  UChosen[2] := (Pos(',all,', P) > 0) or (Pos(',subs,', P) > 0);
  UChosen[3] := (Pos(',all,', P) > 0) or (Pos(',books,', P) > 0);
  for I := 0 to 3 do
    UChosen[I] := UChosen[I] and UOffer[I];
end;

function InitializeUninstall(): Boolean;
begin
  LocateData();
  if UninstallSilent() then
  begin
    ChooseFromParam();
    Result := True;
  end
  else
    Result := ChooseRemovals();
end;

procedure StopServer();
var
  App, Cmd: String;
  Code: Integer;
begin
  App := ExpandConstant('{app}\python\');
  if not DirExists(App) then
    Exit;
  StringChangeEx(App, '''', '''''', True);
  Cmd := '-NoProfile -NonInteractive -Command "' +
         'Get-Process -ErrorAction SilentlyContinue | ' +
         'Where-Object { $_.Path -and $_.Path.StartsWith(''' + App + ''', ''OrdinalIgnoreCase'') } | ' +
         'Stop-Process -Force -ErrorAction SilentlyContinue; ' +
         'for ($i = 0; $i -lt 20; $i++) { ' +
         '  if (-not (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith(''' + App + ''', ''OrdinalIgnoreCase'') })) { break } ' +
         '  Start-Sleep -Milliseconds 200 ' +
         '}"';
  Log('Stopping Aobana: ' + Cmd);
  if Exec(ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'), Cmd, '', SW_HIDE,
          ewWaitUntilTerminated, Code) then
    Log('Stop exit code ' + IntToStr(Code))
  else
    Log('Stop could not start PowerShell: ' + SysErrorMessage(Code));
  Sleep(300);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopServer();
  Result := '';
end;

procedure NoteLeft(Path: String; var Left: String);
begin
  if FileExists(Path) or DirExists(Path) then
    Left := Left + Path + #13#10;
end;

procedure DeleteFolderRetry(Dir: String; Only: Boolean);
var
  I, Code: Integer;
  Flags: String;
begin
  for I := 1 to 10 do
  begin
    if Only then
      RemoveDir(Dir)
    else
      DelTree(Dir, True, True, True);
    if not DirExists(Dir) then
      Exit;
    Sleep(300);
  end;
  if Only then
    Flags := ''
  else
    Flags := '/S /Q ';
  Exec(ExpandConstant('{cmd}'), '/C rmdir ' + Flags + '"' + Dir + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('Folder still there after retries, rmdir: ' + Dir + ', exit ' + IntToStr(Code) +
      ', gone ' + IntToStr(Ord(not DirExists(Dir))));
end;

procedure DeleteFolder(Dir: String);
begin
  DeleteFolderRetry(Dir, False);
end;

procedure RemoveEmptyFolder(Dir: String);
begin
  DeleteFolderRetry(Dir, True);
end;

procedure DeleteSettings(var Left: String);
var
  FR: TFindRec;
  Doomed: TArrayOfString;
  I, N: Integer;
  Own: Boolean;
begin
  N := 0;
  if FindFirst(UStore + '\*', FR) then
    try
      repeat
        Own := (FR.Name = '.') or (FR.Name = '..') or (CompareText(FR.Name, 'db') = 0);
        if not Own then
        begin
          SetArrayLength(Doomed, N + 1);
          Doomed[N] := AddBackslash(UStore) + FR.Name;
          N := N + 1;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  for I := 0 to N - 1 do
  begin
    if DirExists(Doomed[I]) then
      DelTree(Doomed[I], True, True, True)
    else
      DeleteFile(Doomed[I]);
    NoteLeft(Doomed[I], Left);
  end;
end;

procedure RemoveChosen();
var
  Left: String;
begin
  Left := '';
  if UChosen[0] and UChosen[1] then
  begin
    DelTree(UStore, True, True, True);
    NoteLeft(UStore, Left);
  end
  else
  begin
    if UChosen[0] then
      DeleteSettings(Left);
    if UChosen[1] then
    begin
      DelTree(UDb, True, True, True);
      NoteLeft(UDb, Left);
    end;
    RemoveDir(UStore);
  end;
  if UChosen[2] then
  begin
    DeleteFolder(USubs);
    NoteLeft(USubs, Left);
  end;
  if UChosen[3] then
  begin
    DeleteFolder(UBooks);
    NoteLeft(UBooks, Left);
  end;
  if UChosen[2] or UChosen[3] then
    RemoveEmptyFolder(ExpandConstant('{userdocs}\Aobana'));
  Log('Uninstall removed: settings=' + IntToStr(Ord(UChosen[0])) + ' index=' + IntToStr(Ord(UChosen[1])) +
      ' subs=' + IntToStr(Ord(UChosen[2])) + ' books=' + IntToStr(Ord(UChosen[3])));
  if (Left <> '') and not UninstallSilent() then
    MsgBox(FmtMessage(CustomMessage('UninstLeft'), [Left]), mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopServer()
  else if CurUninstallStep = usPostUninstall then
    RemoveChosen();
end;
