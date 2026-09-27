# usage guide (bes2300* audio prompt patcher module)

### prerequisites

1.  **firmware file:** it'll be downloaded in the patcher menu, or you can download the firmware file of your bes2300* device [here](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md).
2.  **custom sounds:** prepare the audio files you want to use. they can be in `.wav`.

    > **tip:** you can use my custom minimal sound pack available in the `sound_packs` directory as a starting point!

### step 1: prepare your files

1.  **name your sounds:** you must name your custom sound files according to the following id table. the patcher uses these exact filenames to know which sound to replace.

    | filename | description |
    | :--- | :--- |
    | `ID_00.wav` | power on |
    | `ID_01.wav` | power off |
    | `ID_13.wav` | pairing mode / device disconnected |
    | `ID_15.wav` | successfully connected |
    | `ID_23.wav` | low battery |
    | `ID_29.wav` | maximum volume warning |
    | `ID_37.wav` | battery fully charged (battery high) |
    | `ID_38.wav` | battery medium |
    | `ID_40.wav` | ANC on |
    | `ID_41.wav` | ANC off (normal mode) |
    | `ID_42.wav` | transparency mode |

2.  **create the sounds directory:** create a folder named `sounds_src` in the `patcher` directory and place all your named sound files inside it.

### step 2: run the patcher

#### GUI guide
1. open the `openqore` .exe file.
2. select or download the firmware from catalog.
3. select the `2300* audio prompt patcher` module. 
4. change the module & sounds patch options if needed. i recommend setting the sample rate to 32kHz.
5. patch the firmware.

#### CLI guide
1.  open your terminal in the `openqore/patcher` directory.
2.  run the script using the command:
    ```
    python main.py --cli
    ```
3. you will be presented with a menu of available patches. select the option for "patch audio prompts".
4. select the `2300* audio prompt patcher` module.
5. change the module & sounds patch options if needed. i recommend setting the sample rate to 32kHz.
6. patch the firmware.

    > **warning!** if you keep the stock sounds but change the sample rate, they'll speed up, so it's recommended to mute them.

### step 3: enjoy!

congratulations! a patched fimrware has been created.

now you can [flash](../UART_things/FLASH_MP.md) this file back to your headphones.
