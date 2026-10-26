on run argv
    set kind to item 1 of argv
    if kind is "keys" then
        return POSIX path of (choose file with prompt "Step 2/3: Select your prod.keys file (not title.keys).")
    else if kind is "output" then
        return POSIX path of (choose folder with prompt "Step 3/3: Select the folder for the complete unsigned IPA.")
    else
        return POSIX path of (choose folder with prompt "Step 1/3: Select one game's folder containing its base NSP/XCI, update and optional DLC. Registered games and versions come from dm/games.")
    end if
end run
