# select_files_uia.ps1 -- multi-select items inside a Windows file dialog via UI Automation.
#
# Why this exists: in the Windows "Open" dialog, clicking the Open button with a wildcard
# ("*.pdf") in the File name box does nothing -- the shell only expands a wildcard on Enter,
# and Enter cannot be sent here (the host refuses to activate a window, so no foreground key
# input). SelectionItemPattern.Select()/AddToSelection() on the list items is the reliable path.
# After selecting, the shell itself writes the quoted file list into the File name box, so the
# next step is just: press "Open(O)" via the computer-use tool.
#
# The item list is VIRTUALIZED: FindAll returns only the ~15 realized rows. To submit more files
# than that, move the targets into an otherwise-empty folder first, submit, then move them back.
#
# This file is intentionally ASCII-only: PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# comments or string literals break parsing on some systems.

param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    # Comma-separated ASCII suffixes to match, e.g. "_1_1-164,_2_165-328".
    # Empty means: select every realized list item in the dialog.
    [string]$Suffix = '',
    # Print what would be selected without touching anything.
    [switch]$ListOnly
)

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$Cond = [System.Windows.Automation.Condition]
$SI = [System.Windows.Automation.SelectionItemPattern]
$root = $AE::RootElement

function Show-Str($s) {
    if ($null -eq $s) { return '<null>' }
    $out = ''
    foreach ($ch in $s.ToCharArray()) {
        if ([int][char]$ch -lt 128) { $out += $ch } else { $out += ('\u{0:x4}' -f [int][char]$ch) }
    }
    return $out
}

$suffixes = @()
if ($Suffix -ne '') {
    foreach ($s in $Suffix.Split(',')) {
        $t = $s.Trim()
        if ($t -ne '') { $suffixes += $t }
    }
}

$procCond = New-Object System.Windows.Automation.PropertyCondition($AE::ProcessIdProperty, $ProcessId)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $procCond)
if ($wins.Count -eq 0) {
    Write-Output "ERROR: no top-level window found for pid $ProcessId (is the app running?)"
    exit 1
}

$items = @()
foreach ($w in $wins) {
    $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $Cond::TrueCondition)
    foreach ($i in $all) {
        if ($i.Current.ControlType.ProgrammaticName -eq 'ControlType.ListItem') { $items += $i }
    }
}
Write-Output ("realized list items: " + $items.Count)

$targets = @()
foreach ($it in $items) {
    $nm = $it.Current.Name
    if ($suffixes.Count -eq 0) {
        $targets += $it
        continue
    }
    foreach ($s in $suffixes) {
        if ($nm.EndsWith($s)) { $targets += $it; break }
    }
}
Write-Output ("matched targets: " + $targets.Count)
foreach ($t in $targets) { Write-Output ("  target: " + (Show-Str $t.Current.Name)) }

if ($targets.Count -eq 0) {
    Write-Output "nothing matched -- wrong folder, or the list has not loaded yet"
    exit 2
}

if ($ListOnly) {
    Write-Output "ListOnly: no selection performed"
    exit 0
}

$first = $true
$ok = 0
$fail = 0
foreach ($t in $targets) {
    try {
        $p = $t.GetCurrentPattern($SI::Pattern)
        if ($first) { $p.Select(); $first = $false } else { $p.AddToSelection() }
        $ok++
    } catch {
        $fail++
        Write-Output ("  select failed: " + (Show-Str $t.Current.Name) + " -> " + $_.Exception.Message)
    }
}
Write-Output ("select ok=$ok fail=$fail")

$sel = 0
foreach ($t in $targets) {
    try { if ($t.GetCurrentPattern($SI::Pattern).Current.IsSelected) { $sel++ } } catch { }
}
Write-Output ("verified selected: $sel")

if ($sel -eq $targets.Count) {
    Write-Output "OK: the shell should now show the quoted file list in the 'File name' box."
    Write-Output "Next: press the Open(O) button with the computer-use tool."
} else {
    Write-Output "WARNING: selection count mismatch, do not press Open yet"
}
