<h1 align="center">
  openqore
  <br>
  <img src=".github/open-qore-logo.png" width="40" alt="open-qore logo"> 
</h1>

an open-source toolkit to patch, modify, and enhance the firmware of headphones based on the BES chipsets (originally started from the soundcore Q35), with future support for other models planned.

> **note:** this project is my personal journey into the world of hardware reverse-engineering and embedded systems. expect bugs, mistakes, and lots of fun. all contributions and advice are welcome!

<p align="center">
  <a href="https://github.com/nnonickreal/openqore"><img src="https://img.shields.io/badge/status-in%20development-orange?style=for-the-badge" alt="Status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/nnonickreal/openqore?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/nnonickreal/openqore/stargazers"><img src="https://img.shields.io/github/stars/nnonickreal/openqore?style=for-the-badge" alt="Stars"></a>
  <a href="https://github.com/nnonickreal/openqore/issues"><img src="https://img.shields.io/github/issues/nnonickreal/openqore?style=for-the-badge" alt="Issues"></a>
</p>

# important info! (fast navigation)
**do you want to:**

* patch your headphones' firmware? -> qorepatcher (this repository, look below for quick start)
* install / develop the custom firmware? (`soundcore devices based on bes2300p` only at the moment) -> [openqore SDK](https://github.com/nnonickreal/openqore-sdk)
* flash an update / install custom firmware over-the-air? (OTA) -> [OTA files for BES devices](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md) and [besota](https://github.com/nnonickreal/besota) - BES OTA flasher
* flash an update via UART / restore after a bad update or make a backup? -> [hardware flashing guide](docs/UART_things/FLASH_MP.md)


i also created a demo project - a [DOOM port](https://github.com/nnonickreal/DOOMcore) based on the [DOOMBuds](https://github.com/arin-s/DOOMBuds) project. check that out too! =)
<h2 align="center">
  qorepatcher
</h2>

<p align="center">
  <strong><a href="INDEX.md">📚 read the full documentation 📚</a></strong>
</p>

## supported devices

this project was started with the soundcore Life Q35. if you want to help test or add support for a new model, please open an issue or DM me (read [contact](#contact--community))!

read [roadmaps and models](docs/roadmaps/RMS.md) for chips & models support status.

### project roadmap

- [x] initial firmware patcher for sound replacement.
- [x] make patcher to work with all bes2300* chipsets (**warning! needs testing**)
- [ ] make patcher to work with all (or the most) bes chipsets
- [x] create a user-friendly GUI for the patcher.
- [x] reverse-engineer the OTA (over-the-air) update protocol for wireless flashing. (see [besota](https://github.com/nnonickreal/besota))
- [ ] document the firmware structure and key functions.
- [ ] develop a library of community-created sound packs.

## quick start

this guide assumes you have `python` and `git` installed on your system if you're on linux or using CLI mode.

**1. download latest release from [releases](https://github.com/nnonickreal/openqore/releases/latest) and open the .exe file.**

**2. install dependencies (only for CLI, linux and building)**

the patcher requires FFmpeg for audio conversion and pybluez:

**windows:** 
```
pip install git+https://github.com/pybluez/pybluez.git
winget install ffmpeg
```

**macos:**
```
pip install git+https://github.com/pybluez/pybluez.git
brew install ffmpeg
```

**ubuntu/debian:**
```
pip install git+https://github.com/pybluez/pybluez.git
sudo apt install ffmpeg
```

**3. get your firmware file**

click on "Browse firmware archive" and download the firmware (or select "patch firmware" -> "download from online archive" option in CLI).

also, you can download the OTA image [here](https://github.com/nnonickreal/openBES/blob/main/archive/FIRMWARES.md) or read the flash with UART:

[➡️ hardware guide: connecting via UART](docs/UART_things/FLASH_MP.md)

reading the flash via ota (over-the-air) is planned for a future update. (if it's possible :D)

**4. congrats!**

you can find usage instructions [here](docs/USAGE.md)

## faq
<details>
  <summary>1. which option of the firmware (w/o OTA boot or with it) in qorepatcher i should select?</summary>
<br>
  if you're patching the flash dump of the headphones, select the "with OTA boot" option.
  
  if you have downloaded the OTA update image from the official update servers, select the "without OTA boot" option.

  **note:** if you have patched the firmware without OTA boot, you need to [append the OTA boot offset](docs/OTA_things/OTABOOT.md) before [flashing via UART (bestool).](docs/UART_things/FLASHING.md) you do **NOT** need this if you're using the [besota](https://github.com/nnonickreal/besota) script!
</details>

## contributing

contributions are what make the open source community such an amazing place to learn, inspire, and create. any contributions you make are **greatly appreciated**.

also, check the [module creating guide](docs/contributing_guides/MODULE_SYS.md)!

if you have a suggestion that would make this better, please fork the repo and create a pull request. you can also simply open an issue with the tag "enhancement".
don't forget to give the project a star! thanks again!

1.  fork the project.
2.  create your feature branch (`git checkout -b feature/amazing-feature`).
3.  commit your changes (`git commit -m 'feat: add some amazing feature'`).
4.  push to the branch (`git push origin feature/amazing-feature`).
5.  open a pull request.

## contact & community

<p align="left">
  <a href="https://t.me/nnonick" target="_blank"><img src="https://img.shields.io/badge/telegram-%40nnonick-2CA5E0?style=for-the-badge&logo=telegram" alt="telegram"></a>
  <a href="https://discord.gg/EPjhKzUHVq" target="_blank"><img src="https://img.shields.io/badge/discord-join_chat-5865F2?style=for-the-badge&logo=discord" alt="discord server"></a>
</p>

## ❤️ support the project

if you find this project helpful and want to support its future development, you can treat me to a coffee or some snacks via boosty! every contribution is greatly appreciated and helps me dedicate more time to openqore.

<p>
  <a href="https://boosty.to/nnonick" target="_blank"><img src="https://img.shields.io/badge/support_me_on-boosty-FF8100?style=for-the-badge&logo=boosty&logoColor=white" alt="Boosty"></a>
</p>

## acknowledgements

this project was brought to life with the extensive use of ai-powered coding assistants. while the core reverse-engineering, research, and architectural decisions were made by the author, ai played a crucial role in accelerating the development process, writing boilerplate code, and debugging.

this is a modern project built with modern tools.

## license

this project is licensed under the GPLv3 license. you can find the full license text in the [license](LICENSE) file.
