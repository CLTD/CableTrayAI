using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Microsoft.Win32;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CableTrayAIInstaller
{
    internal static class Program
    {
        private const string AppName = "CableTrayAI";
        private const string Publisher = "CNPE";
        private const string UninstallKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CableTrayAI";

        private static readonly HashSet<string> ExcludedDirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".git",
            ".pytest_cache",
            ".pytest_tmp",
            "__pycache__",
            "jobs",
            "uploads",
            "outputs",
            "logs",
            "_internal_update",
            "_review_pre_real"
        };

        private static readonly HashSet<string> ManagedDirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".agents",
            "apps",
            "config",
            "core",
            "data",
            "docs",
            "prompts",
            "runtime",
            "scripts",
            "source_materials",
            "templates",
            "tests"
        };

        private static readonly HashSet<string> RuntimeDataDirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "jobs",
            "uploads",
            "outputs",
            "logs"
        };

        private static readonly HashSet<string> ManagedRootFiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".gitignore",
            "AGENTS.md",
            "CableTrayAI.exe",
            "CableTrayAI_Installer.exe",
            "CableTrayAI_Uninstall.exe",
            "README.md",
            "install_manifest.json",
            "pyproject.toml",
            "requirements.txt"
        };

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            if (HasArg(args, "/uninstall") || HasArg(args, "--uninstall"))
            {
                return RunUninstall(args);
            }
            return RunInstall();
        }

        private static int RunInstall()
        {
            string packageRoot = ResolvePackageRoot();
            try
            {
                Log(packageRoot, "CableTrayAI native installer started.");
                Log(packageRoot, "Package root: " + packageRoot);

                string installDir = ResolveInstallDir(packageRoot);
                if (string.IsNullOrWhiteSpace(installDir))
                {
                    Log(packageRoot, "Install cancelled.");
                    return 0;
                }

                installDir = Path.GetFullPath(installDir);
                if (SamePath(packageRoot, installDir))
                {
                    throw new InvalidOperationException("The installation folder must be different from the package folder.");
                }

                Log(packageRoot, "Selected install dir: " + installDir);
                StopOldProcesses();
                if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_CLEAN_PREVIOUS_REGISTERED_INSTALL"), "1", StringComparison.OrdinalIgnoreCase))
                {
                    CleanupPreviousRegisteredInstallIfDifferent(installDir);
                }
                else
                {
                    Log(packageRoot, "Previous registered install cleanup skipped by default.");
                }
                CleanupExistingInstall(installDir);
                CopyPackage(packageRoot, installDir);
                AuthSetup authSetup = EnsureAuthLocal(installDir, packageRoot);
                EnsureLoginInfoFile(installDir, authSetup);
                EnsureDesktopExecutable(installDir);
                string shortcut = CreateDesktopShortcut(installDir);
                string uninstallExe = CopySelfAsUninstaller(installDir);
                string startMenuShortcut = CreateStartMenuShortcut(installDir);
                string uninstallShortcut = CreateStartMenuUninstallShortcut(installDir, uninstallExe);
                RegisterUninstaller(installDir, uninstallExe);
                WriteManifest(installDir, packageRoot, shortcut, startMenuShortcut, uninstallShortcut, uninstallExe, authSetup);

                if (!QuietMode())
                {
                    string loginMessage = authSetup.Created
                        ? "\n\nInitial login users: " + string.Join(", ", authSetup.Users.ToArray()) + "\nInitial password: " + authSetup.InitialPassword
                        : "\n\nExisting local login config was kept:\n" + authSetup.Path;
                    loginMessage += "\n\nLogin info file:\n" + authSetup.LoginInfoPath;
                    MessageBox.Show(
                        "CableTrayAI has been installed.\n\nInstall folder:\n" + installDir + "\n\nDesktop shortcut:\n" + shortcut + loginMessage,
                        "CableTrayAI Installer",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }

                Log(packageRoot, "Install completed.");
                return 0;
            }
            catch (Exception ex)
            {
                Log(packageRoot, "Install failed: " + ex);
                if (!QuietMode())
                {
                    MessageBox.Show(
                        "CableTrayAI installation failed.\n\n" + ex.Message + "\n\nPlease contact administrator-duxyb.",
                        "CableTrayAI Installer",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
                return 1;
            }
        }

        private static bool QuietMode()
        {
            if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_INSTALLER_QUIET"), "1", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            return HasArg(Environment.GetCommandLineArgs(), "/quiet") || HasArg(Environment.GetCommandLineArgs(), "--quiet");
        }

        private static bool HasArg(string[] args, string value)
        {
            foreach (string arg in args)
            {
                if (string.Equals(arg, value, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private static int RunUninstall(string[] args)
        {
            string installDir = ResolveInstallDirForUninstall();
            try
            {
                bool keepData = !HasArg(args, "/remove-data") && !HasArg(args, "--remove-data");
                if (!QuietMode())
                {
                    using (UninstallForm form = new UninstallForm(installDir))
                    {
                        DialogResult result = form.ShowDialog();
                        if (result != DialogResult.OK)
                        {
                            return 0;
                        }
                        keepData = form.KeepData;
                    }
                }

                StopOldProcesses();
                DeleteDesktopShortcut();
                DeleteStartMenuFolder();
                UnregisterUninstaller();
                if (keepData)
                {
                    CleanupExistingInstall(installDir);
                    Directory.CreateDirectory(installDir);
                    File.WriteAllText(
                        Path.Combine(installDir, "uninstall_manifest.json"),
                        "{\n  \"status\": \"program_removed_data_kept\",\n  \"removed_at\": \"" + Escape(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")) + "\"\n}\n",
                        Encoding.UTF8);
                    DeleteFileLater(Application.ExecutablePath);
                }
                else
                {
                    DeleteInstallTreeLater(installDir);
                }

                if (!QuietMode())
                {
                    MessageBox.Show(
                        keepData
                            ? "CableTrayAI has been uninstalled. Local jobs, uploads, outputs, and local configs were kept."
                            : "CableTrayAI has been uninstalled. Local program and data folders are scheduled for removal.",
                        "CableTrayAI Uninstaller",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
                return 0;
            }
            catch (Exception ex)
            {
                if (!QuietMode())
                {
                    MessageBox.Show(
                        "CableTrayAI uninstall failed.\n\n" + ex.Message + "\n\nPlease contact administrator-duxyb.",
                        "CableTrayAI Uninstaller",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
                return 1;
            }
        }

        private static string ResolveInstallDirForUninstall()
        {
            string env = Environment.GetEnvironmentVariable("CABLETRAYAI_INSTALL_DIR");
            if (!string.IsNullOrWhiteSpace(env))
            {
                return Path.GetFullPath(env);
            }
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(UninstallKeyPath))
                {
                    object value = key == null ? null : key.GetValue("InstallLocation");
                    if (value != null && !string.IsNullOrWhiteSpace(Convert.ToString(value)))
                    {
                        return Path.GetFullPath(Convert.ToString(value));
                    }
                }
            }
            catch
            {
            }
            return AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }

        private static string ResolvePackageRoot()
        {
            DirectoryInfo exeDir = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            if (string.Equals(exeDir.Name, "CableTrayAI_Installer", StringComparison.OrdinalIgnoreCase)
                && exeDir.Parent != null
                && string.Equals(exeDir.Parent.Name, "runtime", StringComparison.OrdinalIgnoreCase)
                && exeDir.Parent.Parent != null)
            {
                return exeDir.Parent.Parent.FullName.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            }
            return exeDir.FullName.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }

        private static string ResolveInstallDir(string packageRoot)
        {
            string env = Environment.GetEnvironmentVariable("CABLETRAYAI_INSTALL_DIR");
            if (!string.IsNullOrWhiteSpace(env))
            {
                return env;
            }

            using (InstallForm form = new InstallForm(DefaultInstallDir()))
            {
                DialogResult result = form.ShowDialog();
                if (result != DialogResult.OK)
                {
                    return null;
                }
                return form.InstallDir;
            }
        }

        private static string DefaultInstallDir()
        {
            string previous = ResolvePreviousRegisteredInstallDir();
            if (!string.IsNullOrWhiteSpace(previous))
            {
                return previous;
            }
            if (Directory.Exists(@"D:\"))
            {
                return @"D:\CableTrayAI";
            }
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CableTrayAI");
        }

        private static string ResolvePreviousRegisteredInstallDir()
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(UninstallKeyPath))
                {
                    object value = key == null ? null : key.GetValue("InstallLocation");
                    string text = value == null ? "" : Convert.ToString(value);
                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        return Path.GetFullPath(text);
                    }
                }
            }
            catch
            {
            }
            return "";
        }

        private static void CleanupPreviousRegisteredInstallIfDifferent(string installDir)
        {
            string previous = ResolvePreviousRegisteredInstallDir();
            if (string.IsNullOrWhiteSpace(previous) || SamePath(previous, installDir))
            {
                return;
            }
            try
            {
                CleanupExistingInstall(previous);
                Log(ResolvePackageRoot(), "Previous registered install cleaned: " + previous);
            }
            catch (Exception ex)
            {
                Log(ResolvePackageRoot(), "Previous registered install cleanup skipped: " + ex.Message);
            }
        }

        private static void StopOldProcesses()
        {
            if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_SKIP_PROCESS_STOP"), "1", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }
            foreach (string processName in new[] { "CableTrayAI", "CableTrayAI_Server" })
            {
                foreach (Process process in Process.GetProcessesByName(processName))
                {
                    try
                    {
                        process.Kill();
                        process.WaitForExit(3000);
                    }
                    catch
                    {
                    }
                }
            }
            Thread.Sleep(300);
        }

        private static void CleanupExistingInstall(string installDir)
        {
            Directory.CreateDirectory(installDir);

            Dictionary<string, string> localConfigBackup = BackupLocalConfigs(installDir);
            string feedbackBackup = BackupOperatorFeedback(installDir);

            foreach (string dir in ManagedDirs)
            {
                string target = Path.Combine(installDir, dir);
                if (Directory.Exists(target))
                {
                    Directory.Delete(target, true);
                }
            }

            if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_RESET_RUNTIME_DATA"), "1", StringComparison.OrdinalIgnoreCase))
            {
                foreach (string dir in RuntimeDataDirs)
                {
                    string target = Path.Combine(installDir, dir);
                    if (Directory.Exists(target))
                    {
                        Directory.Delete(target, true);
                    }
                }
            }

            foreach (string file in Directory.GetFiles(installDir))
            {
                string name = Path.GetFileName(file);
                string ext = Path.GetExtension(file);
                if (ManagedRootFiles.Contains(name) || string.Equals(ext, ".cmd", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(ext, ".ps1", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(ext, ".toml", StringComparison.OrdinalIgnoreCase))
                {
                    TryDeleteFile(file);
                }
            }

            RestoreLocalConfigs(installDir, localConfigBackup);
            RestoreOperatorFeedback(installDir, feedbackBackup);
        }

        private static Dictionary<string, string> BackupLocalConfigs(string installDir)
        {
            Dictionary<string, string> backup = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            string config = Path.Combine(installDir, "config");
            if (!Directory.Exists(config))
            {
                return backup;
            }

            foreach (string file in Directory.GetFiles(config, "*.*", SearchOption.TopDirectoryOnly))
            {
                string name = Path.GetFileName(file);
                if (name.IndexOf(".local", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    backup[name] = File.ReadAllText(file, Encoding.UTF8);
                }
            }
            return backup;
        }

        private static void RestoreLocalConfigs(string installDir, Dictionary<string, string> backup)
        {
            if (backup.Count == 0)
            {
                return;
            }
            string config = Path.Combine(installDir, "config");
            Directory.CreateDirectory(config);
            foreach (KeyValuePair<string, string> item in backup)
            {
                File.WriteAllText(Path.Combine(config, item.Key), item.Value, Encoding.UTF8);
            }
        }

        private static string BackupOperatorFeedback(string installDir)
        {
            string feedback = Path.Combine(installDir, "docs", "operator_feedback");
            if (!Directory.Exists(feedback))
            {
                return null;
            }
            string temp = Path.Combine(Path.GetTempPath(), "CableTrayAI_feedback_" + Guid.NewGuid().ToString("N"));
            CopyDirectory(feedback, temp, false);
            return temp;
        }

        private static void RestoreOperatorFeedback(string installDir, string backup)
        {
            if (string.IsNullOrEmpty(backup) || !Directory.Exists(backup))
            {
                return;
            }
            string feedback = Path.Combine(installDir, "docs", "operator_feedback");
            CopyDirectory(backup, feedback, false);
            TryDeleteDirectory(backup);
        }

        private static void CopyPackage(string sourceRoot, string installDir)
        {
            foreach (string entry in Directory.GetFileSystemEntries(sourceRoot))
            {
                if (ShouldSkip(entry, sourceRoot))
                {
                    continue;
                }

                string target = Path.Combine(installDir, Path.GetFileName(entry));
                if (Directory.Exists(entry))
                {
                    CopyDirectory(entry, target, true, sourceRoot);
                }
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Copy(entry, target, true);
                }
            }
        }

        private static void EnsureDesktopExecutable(string installDir)
        {
            string rootExe = Path.Combine(installDir, "CableTrayAI.exe");
            if (File.Exists(rootExe))
            {
                return;
            }
            string runtimeExe = Path.Combine(installDir, "runtime", "CableTrayAI_Desktop", "CableTrayAI.exe");
            if (File.Exists(runtimeExe))
            {
                File.Copy(runtimeExe, rootExe, true);
            }
        }

        private static AuthSetup EnsureAuthLocal(string installDir, string packageRoot)
        {
            string configDir = Path.Combine(installDir, "config");
            Directory.CreateDirectory(configDir);
            string authLocal = Path.Combine(configDir, "auth.local.json");
            List<string> users = InitialUsers();
            InitialPasswordChoice passwordChoice = ResolveInitialPassword(packageRoot);
            if (File.Exists(authLocal) && !passwordChoice.FixedByDeployment)
            {
                return new AuthSetup
                {
                    Created = false,
                    Path = authLocal,
                    Users = users,
                    InitialPassword = "",
                    PasswordSource = "existing"
                };
            }

            string initialPassword = passwordChoice.Password;
            if (File.Exists(authLocal) && passwordChoice.FixedByDeployment)
            {
                BackupExistingAuthLocal(authLocal);
            }

            StringBuilder usersJson = new StringBuilder();
            for (int i = 0; i < users.Count; i++)
            {
                if (i > 0)
                {
                    usersJson.Append(",\n");
                }
                string username = users[i];
                usersJson.Append("    { \"username\": \"")
                    .Append(Escape(username))
                    .Append("\", \"password_hash\": \"")
                    .Append(PasswordHash(username, initialPassword))
                    .Append("\" }");
            }

            string payload = "{\n"
                + "  \"enabled\": true,\n"
                + "  \"session_ttl_seconds\": 43200,\n"
                + "  \"users\": [\n"
                + usersJson
                + "\n  ],\n"
                + "  \"note\": \"Local machine credential file generated by CableTrayAI installer. Do not publish or commit.\"\n"
                + "}\n";
            File.WriteAllText(authLocal, payload, Encoding.UTF8);
            return new AuthSetup
            {
                Created = true,
                Path = authLocal,
                Users = users,
                InitialPassword = initialPassword,
                PasswordSource = passwordChoice.Source,
                LoginInfoPath = Path.Combine(installDir, "CableTrayAI_LOGIN_INFO.txt")
            };
        }

        private static InitialPasswordChoice ResolveInitialPassword(string packageRoot)
        {
            string initialPassword = Environment.GetEnvironmentVariable("CABLETRAYAI_INITIAL_PASSWORD");
            if (!string.IsNullOrWhiteSpace(initialPassword))
            {
                return new InitialPasswordChoice
                {
                    Password = initialPassword.Trim(),
                    Source = "environment CABLETRAYAI_INITIAL_PASSWORD",
                    FixedByDeployment = true
                };
            }

            string packagedPasswordPath = Path.Combine(packageRoot, "config", "initial_password.txt");
            if (File.Exists(packagedPasswordPath))
            {
                string packagedPassword = File.ReadAllText(packagedPasswordPath, Encoding.UTF8).Trim();
                if (!string.IsNullOrWhiteSpace(packagedPassword))
                {
                    return new InitialPasswordChoice
                    {
                        Password = packagedPassword,
                        Source = "deployment package config/initial_password.txt",
                        FixedByDeployment = true
                    };
                }
            }

            return new InitialPasswordChoice
            {
                Password = GenerateInitialPassword(),
                Source = "generated random first-install password",
                FixedByDeployment = false
            };
        }

        private static void BackupExistingAuthLocal(string authLocal)
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string backup = authLocal + ".bak_" + stamp;
            File.Copy(authLocal, backup, true);
        }

        private static void EnsureLoginInfoFile(string installDir, AuthSetup authSetup)
        {
            string path = Path.Combine(installDir, "CableTrayAI_LOGIN_INFO.txt");
            authSetup.LoginInfoPath = path;
            if (!authSetup.Created && File.Exists(path))
            {
                return;
            }

            StringBuilder body = new StringBuilder();
            body.AppendLine("CableTrayAI Login Information");
            body.AppendLine("================================");
            body.AppendLine("Install folder: " + installDir);
            body.AppendLine("Login URL: http://127.0.0.1:8000/");
            body.AppendLine("Users: " + string.Join(", ", authSetup.Users.ToArray()));
            if (authSetup.Created)
            {
                body.AppendLine("Initial password: " + authSetup.InitialPassword);
                body.AppendLine("Password status: " + authSetup.PasswordSource + ".");
            }
            else
            {
                body.AppendLine("Password status: existing local auth was preserved; reinstall cannot recover the password.");
            }
            body.AppendLine("Auth config: " + authSetup.Path);
            body.AppendLine("ANSYS config: " + Path.Combine(installDir, "config", "ansys.local.toml"));
            body.AppendLine("");
            body.AppendLine("Keep this file inside the unit machine. Do not publish, upload, or commit it.");
            File.WriteAllText(path, body.ToString(), Encoding.UTF8);
        }

        private static List<string> InitialUsers()
        {
            string usersEnv = Environment.GetEnvironmentVariable("CABLETRAYAI_INITIAL_USERS");
            List<string> users = new List<string>();
            if (!string.IsNullOrWhiteSpace(usersEnv))
            {
                foreach (string item in usersEnv.Split(','))
                {
                    string user = item.Trim().ToLowerInvariant();
                    if (user.Length > 0 && !users.Contains(user))
                    {
                        users.Add(user);
                    }
                }
            }
            if (users.Count == 0)
            {
                users.Add("duxyb");
                users.Add("jianghl");
                users.Add("wanggangb");
            }
            return users;
        }

        private static string GenerateInitialPassword()
        {
            byte[] bytes = new byte[18];
            using (RandomNumberGenerator rng = RandomNumberGenerator.Create())
            {
                rng.GetBytes(bytes);
            }
            return Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', 'A').Replace('/', 'B');
        }

        private static string PasswordHash(string username, string password)
        {
            string material = "CableTrayAI:" + username.Trim().ToLowerInvariant() + ":" + password;
            byte[] bytes = Encoding.UTF8.GetBytes(material);
            using (SHA256 sha = SHA256.Create())
            {
                byte[] digest = sha.ComputeHash(bytes);
                StringBuilder hex = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest)
                {
                    hex.Append(value.ToString("x2"));
                }
                return hex.ToString();
            }
        }

        private static void CopyDirectory(string source, string target, bool honorSkips, string packageRoot = null)
        {
            if (packageRoot == null)
            {
                packageRoot = source;
            }
            Directory.CreateDirectory(target);
            string[] dirs;
            string[] files;
            try
            {
                dirs = Directory.GetDirectories(source);
                files = Directory.GetFiles(source);
            }
            catch (UnauthorizedAccessException)
            {
                return;
            }
            catch (IOException)
            {
                return;
            }

            foreach (string dir in dirs)
            {
                if (honorSkips && ShouldSkip(dir, packageRoot))
                {
                    continue;
                }
                CopyDirectory(dir, Path.Combine(target, Path.GetFileName(dir)), honorSkips, packageRoot);
            }
            foreach (string file in files)
            {
                if (honorSkips && ShouldSkip(file, packageRoot))
                {
                    continue;
                }
                try
                {
                    File.Copy(file, Path.Combine(target, Path.GetFileName(file)), true);
                }
                catch (UnauthorizedAccessException)
                {
                }
                catch (IOException)
                {
                }
            }
        }

        private static bool ShouldSkip(string path, string root)
        {
            string name = Path.GetFileName(path);
            if (string.Equals(name, "__pycache__", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
            string rel = RelativePath(path, root);
            string firstSegment = rel.Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }, StringSplitOptions.RemoveEmptyEntries)[0];
            if (ExcludedDirs.Contains(firstSegment))
            {
                return true;
            }
            if (string.Equals(name, "CableTrayAI_Installer.exe", StringComparison.OrdinalIgnoreCase) && rel.IndexOfAny(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }) < 0)
            {
                return true;
            }
            string extension = Path.GetExtension(path);
            return string.Equals(extension, ".pyc", StringComparison.OrdinalIgnoreCase)
                || string.Equals(extension, ".pyo", StringComparison.OrdinalIgnoreCase);
        }

        private static string RelativePath(string path, string root)
        {
            string fullPath = Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (fullPath.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
            {
                return fullPath.Substring(fullRoot.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            }
            return Path.GetFileName(path);
        }

        private static string CreateDesktopShortcut(string installDir)
        {
            string desktop = Environment.GetEnvironmentVariable("CABLETRAYAI_DESKTOP_DIR");
            if (string.IsNullOrWhiteSpace(desktop))
            {
                desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            }
            Directory.CreateDirectory(desktop);

            string targetExe = Path.Combine(installDir, "CableTrayAI.exe");
            if (!File.Exists(targetExe))
            {
                throw new FileNotFoundException("CableTrayAI.exe was not copied to the installation folder.", targetExe);
            }

            string shortcutPath = Path.Combine(desktop, "CableTrayAI.lnk");
            CreateShortcut(shortcutPath, targetExe, installDir, "CableTrayAI");
            return shortcutPath;
        }

        private static string CopySelfAsUninstaller(string installDir)
        {
            string uninstallExe = Path.Combine(installDir, "CableTrayAI_Uninstall.exe");
            File.Copy(Application.ExecutablePath, uninstallExe, true);
            return uninstallExe;
        }

        private static string StartMenuDir()
        {
            string env = Environment.GetEnvironmentVariable("CABLETRAYAI_START_MENU_DIR");
            if (!string.IsNullOrWhiteSpace(env))
            {
                return env;
            }
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.StartMenu), "Programs", "CableTrayAI");
        }

        private static string CreateStartMenuShortcut(string installDir)
        {
            string dir = StartMenuDir();
            Directory.CreateDirectory(dir);
            string targetExe = Path.Combine(installDir, "CableTrayAI.exe");
            string shortcutPath = Path.Combine(dir, "CableTrayAI.lnk");
            CreateShortcut(shortcutPath, targetExe, installDir, "CableTrayAI");
            return shortcutPath;
        }

        private static string CreateStartMenuUninstallShortcut(string installDir, string uninstallExe)
        {
            string dir = StartMenuDir();
            Directory.CreateDirectory(dir);
            string shortcutPath = Path.Combine(dir, "卸载 CableTrayAI.lnk");
            CreateShortcut(shortcutPath, uninstallExe, installDir, "卸载 CableTrayAI", "/uninstall");
            return shortcutPath;
        }

        private static void CreateShortcut(string shortcutPath, string targetExe, string workingDir, string description, string arguments = "")
        {
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null)
            {
                throw new InvalidOperationException("WScript.Shell is unavailable; cannot create desktop shortcut.");
            }
            object shell = Activator.CreateInstance(shellType);
            object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { shortcutPath });
            Type shortcutType = shortcut.GetType();
            shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { targetExe });
            shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { workingDir });
            shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { description });
            shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { targetExe });
            if (!string.IsNullOrWhiteSpace(arguments))
            {
                shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
            }
            shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
        }

        private static void RegisterUninstaller(string installDir, string uninstallExe)
        {
            if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_SKIP_REGISTRY"), "1", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallKeyPath))
            {
                key.SetValue("DisplayName", "CableTrayAI 电缆桥架力学分析一体化平台");
                key.SetValue("DisplayVersion", "1.0");
                key.SetValue("Publisher", Publisher);
                key.SetValue("InstallLocation", installDir);
                key.SetValue("DisplayIcon", "\"" + Path.Combine(installDir, "CableTrayAI.exe") + "\"");
                key.SetValue("UninstallString", "\"" + uninstallExe + "\" /uninstall");
                key.SetValue("QuietUninstallString", "\"" + uninstallExe + "\" /uninstall /quiet");
                key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
                key.SetValue("EstimatedSize", EstimateDirectorySizeKb(installDir), RegistryValueKind.DWord);
                key.SetValue("URLInfoAbout", "http://127.0.0.1:8000/");
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            }
        }

        private static int EstimateDirectorySizeKb(string root)
        {
            long total = 0;
            try
            {
                foreach (string file in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
                {
                    try
                    {
                        total += new FileInfo(file).Length;
                    }
                    catch
                    {
                    }
                }
            }
            catch
            {
            }
            long kb = Math.Max(1, total / 1024);
            if (kb > int.MaxValue)
            {
                return int.MaxValue;
            }
            return (int)kb;
        }

        private static void UnregisterUninstaller()
        {
            if (string.Equals(Environment.GetEnvironmentVariable("CABLETRAYAI_SKIP_REGISTRY"), "1", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }
            try
            {
                Registry.CurrentUser.DeleteSubKeyTree(UninstallKeyPath, false);
            }
            catch
            {
            }
        }

        private static void DeleteDesktopShortcut()
        {
            string desktop = Environment.GetEnvironmentVariable("CABLETRAYAI_DESKTOP_DIR");
            if (string.IsNullOrWhiteSpace(desktop))
            {
                desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            }
            TryDeleteFile(Path.Combine(desktop, "CableTrayAI.lnk"));
        }

        private static void DeleteStartMenuFolder()
        {
            TryDeleteDirectory(StartMenuDir());
        }

        private static void DeleteInstallTreeLater(string installDir)
        {
            string cmd = Path.Combine(Path.GetTempPath(), "CableTrayAI_uninstall_" + Guid.NewGuid().ToString("N") + ".cmd");
            string body = "@echo off\r\n"
                + "timeout /t 2 /nobreak >nul\r\n"
                + "rmdir /s /q \"" + installDir + "\"\r\n"
                + "del \"%~f0\" >nul 2>nul\r\n";
            File.WriteAllText(cmd, body, Encoding.ASCII);
            Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + cmd + "\"")
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        }

        private static void DeleteFileLater(string file)
        {
            string cmd = Path.Combine(Path.GetTempPath(), "CableTrayAI_delete_" + Guid.NewGuid().ToString("N") + ".cmd");
            string body = "@echo off\r\n"
                + "timeout /t 2 /nobreak >nul\r\n"
                + "del /f /q \"" + file + "\" >nul 2>nul\r\n"
                + "del \"%~f0\" >nul 2>nul\r\n";
            File.WriteAllText(cmd, body, Encoding.ASCII);
            Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + cmd + "\"")
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                WindowStyle = ProcessWindowStyle.Hidden
            });
        }

        private static void WriteManifest(string installDir, string packageRoot, string shortcut, string startMenuShortcut, string uninstallShortcut, string uninstallExe, AuthSetup authSetup)
        {
            StringBuilder usersJson = new StringBuilder();
            for (int i = 0; i < authSetup.Users.Count; i++)
            {
                if (i > 0)
                {
                    usersJson.Append(", ");
                }
                usersJson.Append("\"").Append(Escape(authSetup.Users[i])).Append("\"");
            }
            string json = "{\n"
                + "  \"status\": \"pass\",\n"
                + "  \"installed_at\": \"" + Escape(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")) + "\",\n"
                + "  \"install_dir\": \"" + Escape(installDir) + "\",\n"
                + "  \"package_root\": \"" + Escape(packageRoot) + "\",\n"
                + "  \"shortcut\": \"" + Escape(shortcut) + "\",\n"
                + "  \"start_menu_shortcut\": \"" + Escape(startMenuShortcut) + "\",\n"
                + "  \"uninstall_shortcut\": \"" + Escape(uninstallShortcut) + "\",\n"
                + "  \"uninstaller\": \"" + Escape(uninstallExe) + "\",\n"
                + "  \"entry\": \"desktop shortcut -> CableTrayAI.exe\",\n"
                + "  \"auth_policy\": \"account_login_only\",\n"
                + "  \"auth_local_path\": \"" + Escape(authSetup.Path) + "\",\n"
                + "  \"login_info_path\": \"" + Escape(authSetup.LoginInfoPath) + "\",\n"
                + "  \"auth_local_created\": " + (authSetup.Created ? "true" : "false") + ",\n"
                + "  \"login_users\": [" + usersJson + "]"
                + (authSetup.Created ? ",\n  \"initial_password\": \"" + Escape(authSetup.InitialPassword) + "\",\n  \"initial_password_notice\": \"Local first-install password only. Rotate by rewriting config/auth.local.json.\"" : "")
                + "\n"
                + "}\n";
            File.WriteAllText(Path.Combine(installDir, "install_manifest.json"), json, Encoding.UTF8);
        }

        private static string Escape(string value)
        {
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private static void Log(string packageRoot, string message)
        {
            try
            {
                string logs = Path.Combine(packageRoot, "logs");
                Directory.CreateDirectory(logs);
                File.AppendAllText(Path.Combine(logs, "installer.log"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss ") + message + Environment.NewLine, Encoding.UTF8);
            }
            catch
            {
            }
        }

        private static bool SamePath(string a, string b)
        {
            return string.Equals(Path.GetFullPath(a).TrimEnd('\\'), Path.GetFullPath(b).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
        }

        private static void TryDeleteFile(string path)
        {
            try
            {
                File.Delete(path);
            }
            catch
            {
            }
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                Directory.Delete(path, true);
            }
            catch
            {
            }
        }
    }

    internal sealed class AuthSetup
    {
        public bool Created;
        public string Path;
        public List<string> Users;
        public string InitialPassword;
        public string PasswordSource;
        public string LoginInfoPath;
    }

    internal sealed class InitialPasswordChoice
    {
        public string Password;
        public string Source;
        public bool FixedByDeployment;
    }

    internal sealed class InstallForm : Form
    {
        private readonly TextBox installDirBox;

        public string InstallDir
        {
            get { return installDirBox.Text; }
        }

        public InstallForm(string defaultInstallDir)
        {
            Text = "CableTrayAI 安装程序";
            Width = 640;
            Height = 250;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;

            Label title = new Label();
            title.Text = "安装 CableTrayAI";
            title.Left = 24;
            title.Top = 22;
            title.Width = 560;
            title.Height = 28;
            title.Font = new System.Drawing.Font(title.Font.FontFamily, 13, System.Drawing.FontStyle.Bold);
            Controls.Add(title);

            Label hint = new Label();
            hint.Text = "请选择本地安装目录。安装完成后会创建桌面图标、开始菜单入口和卸载项。";
            hint.Left = 24;
            hint.Top = 58;
            hint.Width = 560;
            hint.Height = 24;
            Controls.Add(hint);

            installDirBox = new TextBox();
            installDirBox.Left = 24;
            installDirBox.Top = 96;
            installDirBox.Width = 450;
            installDirBox.Text = defaultInstallDir;
            Controls.Add(installDirBox);

            Button browse = new Button();
            browse.Text = "浏览...";
            browse.Left = 490;
            browse.Top = 94;
            browse.Width = 100;
            browse.Click += BrowseClick;
            Controls.Add(browse);

            Button install = new Button();
            install.Text = "安装";
            install.Left = 384;
            install.Top = 150;
            install.Width = 100;
            install.DialogResult = DialogResult.OK;
            Controls.Add(install);

            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Left = 490;
            cancel.Top = 150;
            cancel.Width = 100;
            cancel.DialogResult = DialogResult.Cancel;
            Controls.Add(cancel);

            AcceptButton = install;
            CancelButton = cancel;
        }

        private void BrowseClick(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "请选择 CableTrayAI 安装目录";
                dialog.ShowNewFolderButton = true;
                if (Directory.Exists(installDirBox.Text))
                {
                    dialog.SelectedPath = installDirBox.Text;
                }
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    installDirBox.Text = dialog.SelectedPath;
                }
            }
        }
    }

    internal sealed class UninstallForm : Form
    {
        private readonly CheckBox keepDataBox;

        public bool KeepData
        {
            get { return keepDataBox.Checked; }
        }

        public UninstallForm(string installDir)
        {
            Text = "CableTrayAI 卸载程序";
            Width = 660;
            Height = 250;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;

            Label title = new Label();
            title.Text = "卸载 CableTrayAI";
            title.Left = 24;
            title.Top = 22;
            title.Width = 590;
            title.Height = 28;
            title.Font = new System.Drawing.Font(title.Font.FontFamily, 13, System.Drawing.FontStyle.Bold);
            Controls.Add(title);

            Label path = new Label();
            path.Text = "安装目录: " + installDir;
            path.Left = 24;
            path.Top = 58;
            path.Width = 590;
            path.Height = 32;
            Controls.Add(path);

            keepDataBox = new CheckBox();
            keepDataBox.Text = "保留本地 jobs、uploads、outputs、本机配置和操作反馈";
            keepDataBox.Left = 24;
            keepDataBox.Top = 100;
            keepDataBox.Width = 590;
            keepDataBox.Checked = true;
            Controls.Add(keepDataBox);

            Button uninstall = new Button();
            uninstall.Text = "卸载";
            uninstall.Left = 404;
            uninstall.Top = 150;
            uninstall.Width = 100;
            uninstall.DialogResult = DialogResult.OK;
            Controls.Add(uninstall);

            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Left = 510;
            cancel.Top = 150;
            cancel.Width = 100;
            cancel.DialogResult = DialogResult.Cancel;
            Controls.Add(cancel);

            AcceptButton = uninstall;
            CancelButton = cancel;
        }
    }
}
