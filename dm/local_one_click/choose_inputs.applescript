use framework "Foundation"
use scripting additions

-- Follow macOS preferred languages, independently of the game's language.
on promptText(selectionType, preferredLanguage)
    if preferredLanguage starts with "zh" then
        if preferredLanguage contains "Hant" or preferredLanguage contains "TW" or preferredLanguage contains "HK" or preferredLanguage contains "MO" then
            if selectionType is "keys" then return "第 2/3 步：選擇自己的 prod.keys 檔案，不是 title.keys。"
            if selectionType is "output" then return "第 3/3 步：選擇完整未簽名 IPA 的儲存資料夾。"
            return "第 1/3 步：選擇遊戲資料夾，內含本體 NSP/XCI、更新及可選 DLC；也支援 XCI 整合包。"
        else
            if selectionType is "keys" then return "第 2/3 步：选择自己的 prod.keys 文件，不是 title.keys。"
            if selectionType is "output" then return "第 3/3 步：选择完整未签名 IPA 的保存文件夹。"
            return "第 1/3 步：选择游戏文件夹，内含本体 NSP/XCI、更新及可选 DLC；也支持 XCI 整合包。"
        end if
    end if
    if selectionType is "keys" then return "Step 2/3: Select your prod.keys file (not title.keys)."
    if selectionType is "output" then return "Step 3/3: Select the folder for the complete unsigned IPA."
    return "Step 1/3: Select one game's folder containing its base NSP/XCI, update and optional DLC. Integrated XCI is supported."
end promptText

on run argv
    set selectionType to item 1 of argv
    if selectionType is "--self-test" then return "ok"
    set preferredLanguage to "en"
    try
        set preferredLanguage to (current application's NSLocale's preferredLanguages()'s firstObject()) as text
    end try
    -- A noninteractive probe for regression tests; it never opens a panel.
    if selectionType is "--test-prompts" then
        if (count of argv) > 1 then set preferredLanguage to item 2 of argv
        return my promptText("game", preferredLanguage) & linefeed & my promptText("keys", preferredLanguage) & linefeed & my promptText("output", preferredLanguage)
    end if
    set panelPrompt to my promptText(selectionType, preferredLanguage)
    if selectionType is "keys" then
        return POSIX path of (choose file with prompt panelPrompt)
    else
        return POSIX path of (choose folder with prompt panelPrompt)
    end if
end run
