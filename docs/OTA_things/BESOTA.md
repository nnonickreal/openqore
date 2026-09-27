# integrated [besota](https://github.com/nnonickreal/besota) flashing guide

**WARNING! don't even try to flash firmware from other headphones or any other file!**

the flasher includes some security checks, but they **don't** protect against third-party BES firmware! if you do this, there's a 99% chance you'll end up with a bricked device, which can only be fixed via UART and soldering. i am not responsible for any bricked devices.

## GUI guide

1. open the `besota` .exe file or select the `besota` tab in openqore GUI.
2. select your firmware, download it from catalog or click "Flash via besota" button after patching the firmware.
3. specify the OTA_BOOT offset (available in [firmware links](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md)) and the BESOTA protocol (by reading the release date of your headphones and selecting in options).
4. scan for your headphones and connect.
5. flash the update file.
6. after flashing the firmware, the headphones will turn off. **don't touch them for a minute**, and then they should turn on automatically.
7. if they don't turn on, turn them on manually.