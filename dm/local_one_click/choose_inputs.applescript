on run argv
    set selectionType to item 1 of argv
    if selectionType is "--self-test" then return "ok"
    if selectionType is "keys" then
        return POSIX path of (choose file with prompt "Step 2/3: Select your prod.keys file (not title.keys).")
    else if selectionType is "output" then
        return POSIX path of (choose folder with prompt "Step 3/3: Select the folder for the complete unsigned IPA.")
    else
        return POSIX path of (choose folder with prompt "Step 1/3: Select one game's folder containing its base NSP/XCI, update and optional DLC. Registered games and versions come from dm/games.")
    end if
end run
