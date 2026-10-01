using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

static class Aobana
{
    [STAThread]
    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(dir, @"python\pythonw.exe");
        string launcher = Path.Combine(dir, @"aobana\__main__.py");
        if (!File.Exists(python) || !File.Exists(launcher))
        {
            Fail("Aobanaのファイルが見つかりません。再インストールしてください。\n"
               + "Aobana's files are missing. Please reinstall.\n\n"
               + (File.Exists(python) ? launcher : python));
            return 1;
        }
        StringBuilder argv = new StringBuilder("-m aobana");
        foreach (string a in args) argv.Append(' ').Append(Quote(a));
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(python, argv.ToString());
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            Process.Start(psi);
            return 0;
        }
        catch (Exception e)
        {
            Fail("Aobanaを起動できませんでした。\nAobana could not start.\n\n" + e.Message);
            return 1;
        }
    }

    static void Fail(string text)
    {
        MessageBox.Show(text, "Aobana", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    static string Quote(string s)
    {
        if (s.Length > 0 && s.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return s;
        StringBuilder b = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in s)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') b.Append('\\', slashes * 2 + 1);
            else b.Append('\\', slashes);
            slashes = 0;
            b.Append(c);
        }
        b.Append('\\', slashes * 2).Append('"');
        return b.ToString();
    }
}
