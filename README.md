<div align="center">

# 🤖 Charlie AI Assistant

<img src="assets/screenshots/01_Charlie_Hero.png" alt="Charlie AI Assistant Hero" width="100%">

**An intelligent modular AI desktop assistant built with Python, featuring offline voice interaction, a real-time 3D VRM avatar, intelligent memory, and desktop automation.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-4CAF50?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)

[Watch the Demo Video](assets/demo/Charlie_Demo_1080p.mp4) • [Report Bug](https://github.com/harshvardhanj515-beep/charlie-ai-assistant/issues) • [Request Feature](https://github.com/harshvardhanj515-beep/charlie-ai-assistant/issues)

</div>

---

## 🚀 Overview

Charlie is a professional-grade modular AI desktop assistant designed to deliver an intelligent, voice-driven desktop experience completely offline. 

Unlike traditional cloud chatbots, Charlie interacts directly with your local environment, understands natural voice commands, automates repetitive tasks, manages productivity, and communicates through a highly expressive real-time 3D VRM avatar.

Built with a scalable, modular architecture, Charlie is designed to be easily extensible for developers wanting to build their own local AI ecosystem.

---

## ✨ Key Features

- **🎤 Offline Voice Interaction**: Lightning-fast local Wake Word Detection & Speech-to-Text via Whisper.
- **🔊 Natural Text-to-Speech**: High-quality offline voice synthesis.
- **👩 Real-Time 3D Avatar**: Fully integrated VRM 3D model with real-time lip sync and facial expressions.
- **🧠 Intelligent Local Memory**: Contextual long-term and short-term memory utilizing local LLMs.
- **💻 Desktop & Browser Automation**: Control local apps, execute macros, and manipulate web browsers autonomously.
- **📸 Vision Capabilities**: Screenshot analysis and webcam integrations.
- **📅 Productivity Suite**: Built-in Calendar, Task, and Contact management.
- **🔌 Highly Extensible**: Plug-and-play architecture for adding new capability modules.

---

## 📸 Showcase

<div align="center">
  <img src="assets/screenshots/02_Charlie_Listening.png" width="48%">
  <img src="assets/screenshots/03_Charlie_Speaking.png" width="48%">
  <i>Voice Interaction & Speaking Animations</i>
</div>
<br>
<div align="center">
  <img src="assets/screenshots/04_Charlie_Desktop_Control.png" width="48%">
  <img src="assets/screenshots/05_Charlie_Browser_Control.png" width="48%">
  <i>Desktop Automation & Media Control</i>
</div>
<br>
<div align="center">
  <img src="assets/screenshots/06_Charlie_Desktop_Mode.png" width="80%">
  <br>
  <i>Floating Desktop Assistant Mode</i>
</div>

---

## 🏗️ System Architecture

Charlie is structured around a centralized modular brain that routes input and intent to specialized capability modules.

```mermaid
graph TD
    User((User))
    User -->|Voice| STT[Speech-to-Text Module]
    User -->|Text| GUI[UI / Command Line]

    STT --> Brain{Charlie Core / Brain}
    GUI --> Brain

    Brain -->|Memory Storage| DB[(SQLite Database)]
    Brain -->|Natural Language| LLM[Local LLM / Ollama]
    
    Brain -->|Actions| Modules[Capability Modules]
    
    subgraph Capability Modules
        Desktop[Desktop Control]
        Browser[Browser Automation]
        Calendar[Calendar & Tasks]
        Vision[Camera / Screen]
    end
    
    Modules --> Brain
    Brain --> TTS[Text-to-Speech Module]
    TTS --> Engine[Audio Engine]
    TTS --> LipSync[Lip Sync Processor]
    
    LipSync --> VRM[3D Avatar Engine]
    Brain -->|Expressions| VRM
    
    VRM --> Render[Display to User]
```

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.11+
- Windows OS (Linux/macOS support planned)
- [Ollama](https://ollama.ai) installed locally (if using local inference)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/harshvardhanj515-beep/charlie-ai-assistant.git
   cd charlie-ai-assistant
   ```

2. **Set up the virtual environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run Charlie**
   ```bash
   python main.py
   ```

---

## 🗺️ Roadmap

- [x] Base Architecture & Local LLM Integration
- [x] VRM 3D Avatar Engine & Real-Time Lip Sync
- [x] Core Desktop Automation & Browser Control
- [ ] 🎵 Spotify / Media Player Integration
- [ ] 📧 Mail & Calendar Sync (Google Workspace)
- [ ] 🤖 RAG-based Long Term Document Memory
- [ ] ☁️ Cloud Sync Capabilities
- [ ] 📱 Mobile App Companion

---

## 🤝 Contributing

We welcome contributions from the open-source community! 

Please read our [Contributing Guidelines](CONTRIBUTING.md) to get started. Be sure to also review our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## 👨‍💻 Author

**Harshvardhan Jadhav**  
*Python Developer | AI & Automation Enthusiast | Cybersecurity Learner*

Currently building intelligent software, AI assistants, and exploring modern system design.  
If you find this project helpful or inspiring, consider giving it a ⭐!

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
