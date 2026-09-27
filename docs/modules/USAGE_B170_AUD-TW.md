# usage guide (Nothing Headphone (1) system sounds tweaker)

### prerequisites

**warning! this module works only with the 1.0.1.81 firmware at the moment**

1. **firmware file:** it'll be downloaded in the patcher menu, or you can download the firmware file of your Nothing Headphones [here](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md).


### patching system sounds volume

#### GUI guide
1. open the `openqore` .exe file.
2. select or download the firmware from catalog.
3. select the `Nothing Headphone (1)` module.
4. if you need to lower the volume of system sounds, select the fields from 0x0 to 0x5. i recommend selecting 0x3.
5. if you need to adjust the audio stream's ducking (when changing the noise reduction mode), select a value between 10% and 100%. i recommend setting it to 30% or 40%.
6. patch the firmware.

#### CLI guide
1.  open your terminal in the `openqore/patcher` directory.
2.  run the script using the command:
    ```
    python main.py --cli
    ```
3. you will be presented with a menu of available patches. select the option for "patch audio prompts", download the firmware and select the module.
4. if you need to lower the volume of system sounds, select the fields from 0x0 to 0x5. i recommend setting it to 0x3.
5. if you need to adjust the audio stream's ducking (when changing the noise reduction mode), select a value between 10% and 100%. i recommend setting it to 30% or 40%.
6. patch the firmware.

congratulations! a patched fimrware has been created.

now you can [flash](../UART_things/FLASH_MP.md) this file back to your headphones.