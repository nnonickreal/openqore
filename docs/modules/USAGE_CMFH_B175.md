# usage guide (CMF Headphone Pro prompt patcher)

1.  **firmware file:** it'll be downloaded in the patcher menu, or you can download the firmware file of your CMF Headphones [here](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md).
2.  **custom sounds:** prepare the audio files you want to use. they can be in `.wav`.

    > **tip:** you can use my custom minimal sound pack available in the `sound_packs` directory as a starting point!

### step 1: prepare your files

1.  **name your sounds:** you must name your custom sound files according to the following ID table. the patcher uses these exact filenames to know which sound to replace.

    | filename | description |
    | :--- | :--- |
    | `ID_00.wav` | power on |
    | `ID_01.wav` | power off |
    | `ID_03.wav` | concert mode |
    | `ID_04.wav` | ANC off (normal mode) |
    | `ID_06.wav` | successfully connected |
    | `ID_13.wav` | pairing mode |
    | `ID_15.wav` | treble tuning |
    | `ID_16.wav` | minimum volume warning |
    | `ID_17.wav` | volume up |
    | `ID_18.wav` | transparency mode (transparency on) |
    | `ID_20.wav` | low battery |
    | `ID_21.wav` | incoming call |
    | `ID_22.wav` | find my headphones |
    | `ID_23.wav` | 3D audio off |
    | `ID_28.wav` | device disconnected |
    | `ID_52.wav` | ANC on |
    | `ID_57.wav` | volume down |
    | `ID_60.wav` | maximum volume warning |
    | `ID_61.wav` | double press |
    | `ID_62.wav` | triple press |
    | `ID_64.wav` | cinema mode |
    | `ID_67.wav` | bass tuning |
    | `ID_69.wav` | microphone muted |
    | `ID_70.wav` | mic on |
    | `ID_71.wav` | warning tone |

2.  **create the sounds directory:** create a folder named `sounds_src` in the `patcher` directory and place all your named sound files inside it.

### step 2: run the patcher

**warning! do NOT set any sample rate that NOT equals 32000, 48000 or 16000 Hz. it can brick headphones!**

#### GUI guide
1. open the `openqore` .exe file.
2. select or download the firmware from catalog.
3. select the `CMF Headphone Pro patcher` module.
4. change the module & sounds patch options if needed. i recommend setting the sample rate to 32kHz. (32000)
5. patch the firmware.

#### CLI guide
1.  open your terminal in the `openqore/patcher` directory.
2.  run the script using the command:
    ```
    python main.py --cli
    ```
3. you will be presented with a menu of available patches. select the option for "patch audio prompts".
4. select the `CMF Headphone Pro patcher` module.
5. change the module & sounds patch options if needed. i recommend setting the sample rate to 32kHz.
6. patch the firmware.

    > **warning!** if you keep the stock sounds but change the sample rate, they'll speed up, so it's recommended to mute them.

### step 3: enjoy!

congratulations! a patched firmware has been created.

now you can [flash](../UART_things/FLASH_MP.md) this file back to your headphones.
