# Contributing to Charlie AI Assistant

First off, thank you for considering contributing to Charlie! It's people like you that make Charlie such a great tool.

## Where do I go from here?

If you've noticed a bug or have a feature request, make sure to check our [Issues](../../issues) first. If it's a new idea or bug, please open an issue and clearly describe it.

## Setting up your development environment

1. **Fork the repository** to your own GitHub account.
2. **Clone the project** to your local machine:
   ```bash
   git clone https://github.com/YOUR_USERNAME/charlie-ai-assistant.git
   ```
3. **Create a virtual environment** and install the dependencies:
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # On Windows
   pip install -r requirements.txt
   ```
4. **Create a branch** for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Making Changes

- **Code Style**: We try to adhere to standard PEP-8 style guidelines.
- **Modularity**: Try to keep changes modular. If you are adding a new core capability, consider adding it as a standalone module inside the `modules/` directory rather than inflating `main.py`.

## Submitting a Pull Request

1. Commit your changes with a descriptive commit message.
2. Push your branch to your forked repository.
3. Open a Pull Request on the main repository. 
4. Please provide a clear description of the problem your PR solves and how you solved it.

Thank you for contributing!
