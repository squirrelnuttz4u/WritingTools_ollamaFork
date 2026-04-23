"""
AI Provider Architecture for ACNR Intelligence
----------------------------------------------

Minimal provider layer that talks to ACNR's internal Ollama server.

The upstream Writing Tools project also shipped Gemini and OpenAI-compatible
providers; they have been removed in this fork because:
  - the tool must stay on the corporate network (no external LLM vendors),
  - google-generativeai / openai pulled in a huge dependency tree
    (google-auth, cryptography, grpc, protobuf, httpx, etc.) that bloated
    the packaged exe by ~25-30 MB and caused PyInstaller crashes on import.

Key components:
    1. AIProviderSetting - base for settings (e.g. API URL, model name)
       - TextSetting     - single-line text input
       - DropdownSetting - combo box, optional "Custom" free-text entry
    2. AIProvider     - abstract base class all providers implement
    3. OllamaProvider - the only concrete provider

Response flow:
    - The main app calls get_response(system_instruction, prompt).
    - OllamaProvider POSTs to the Ollama /chat endpoint and returns the
      full text synchronously (no streaming).
"""

import logging
import webbrowser
from abc import ABC, abstractmethod
from typing import List

from ollama import Client as OllamaClient
from PySide6 import QtWidgets
from PySide6.QtWidgets import QVBoxLayout

from ui.UIUtils import colorMode


class AIProviderSetting(ABC):
    """Abstract base for a provider setting (API URL, model, etc.)."""

    def __init__(self, name: str, display_name: str = None, default_value: str = None, description: str = None):
        self.name = name
        self.display_name = display_name if display_name else name
        self.default_value = default_value if default_value else ""
        self.description = description if description else ""

    @abstractmethod
    def render_to_layout(self, layout: QVBoxLayout):
        pass

    @abstractmethod
    def set_value(self, value):
        pass

    @abstractmethod
    def get_value(self):
        pass


class TextSetting(AIProviderSetting):
    """Single-line text input (API URL, model name, etc.)."""

    def __init__(self, name: str, display_name: str = None, default_value: str = None, description: str = None):
        super().__init__(name, display_name, default_value, description)
        self.internal_value = default_value
        self.input = None

    def render_to_layout(self, layout: QVBoxLayout):
        row_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(self.display_name)
        label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode=='dark' else '#333333'};")
        row_layout.addWidget(label)
        self.input = QtWidgets.QLineEdit(self.internal_value)
        self.input.setStyleSheet(f"""
            font-size: 16px;
            padding: 5px;
            background-color: {'#444' if colorMode=='dark' else 'white'};
            color: {'#ffffff' if colorMode=='dark' else '#000000'};
            border: 1px solid {'#666' if colorMode=='dark' else '#ccc'};
        """)
        self.input.setPlaceholderText(self.description)
        row_layout.addWidget(self.input)
        layout.addLayout(row_layout)

    def set_value(self, value):
        self.internal_value = value

    def get_value(self):
        return self.input.text()


class DropdownSetting(AIProviderSetting):
    """
    Combo-box setting (e.g. model selection). Optional "Custom" option
    reveals a free-text field when selected; if the loaded config value
    doesn't match any preset, "Custom" is auto-selected.
    """
    _CUSTOM_SENTINEL = "__custom__"

    def __init__(self, name: str, display_name: str = None, default_value: str = None,
                 description: str = None, options: list = None, allow_custom: bool = False,
                 custom_placeholder: str = "Enter custom value"):
        super().__init__(name, display_name, default_value, description)
        self.options = options if options else []
        self.internal_value = default_value
        self.dropdown = None
        self.allow_custom = allow_custom
        self.custom_placeholder = custom_placeholder
        self.custom_input = None
        self.custom_input_container = None

    def render_to_layout(self, layout: QVBoxLayout):
        row_layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(self.display_name)
        label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode=='dark' else '#333333'};")
        row_layout.addWidget(label)
        self.dropdown = QtWidgets.QComboBox()
        self.dropdown.setStyleSheet(f"""
            font-size: 16px;
            padding: 5px;
            background-color: {'#444' if colorMode=='dark' else 'white'};
            color: {'#ffffff' if colorMode=='dark' else '#000000'};
            border: 1px solid {'#666' if colorMode=='dark' else '#ccc'};
        """)

        for option, value in self.options:
            self.dropdown.addItem(option, value)
        if self.allow_custom:
            self.dropdown.addItem("🔧 Custom", self._CUSTOM_SENTINEL)

        index = self.dropdown.findData(self.internal_value)
        if index != -1:
            self.dropdown.setCurrentIndex(index)
        elif self.allow_custom and self.internal_value:
            custom_index = self.dropdown.findData(self._CUSTOM_SENTINEL)
            if custom_index != -1:
                self.dropdown.setCurrentIndex(custom_index)

        row_layout.addWidget(self.dropdown)
        layout.addLayout(row_layout)

        if self.allow_custom:
            self.custom_input_container = QtWidgets.QWidget()
            custom_row_layout = QtWidgets.QHBoxLayout(self.custom_input_container)
            custom_row_layout.setContentsMargins(0, 5, 0, 0)

            self.custom_input = QtWidgets.QLineEdit()
            self.custom_input.setPlaceholderText(self.custom_placeholder)
            self.custom_input.setStyleSheet(f"""
                font-size: 16px;
                padding: 5px;
                background-color: {'#444' if colorMode=='dark' else 'white'};
                color: {'#ffffff' if colorMode=='dark' else '#000000'};
                border: 1px solid {'#666' if colorMode=='dark' else '#ccc'};
            """)
            if self.dropdown.currentData() == self._CUSTOM_SENTINEL and self.internal_value:
                self.custom_input.setText(self.internal_value)

            custom_row_layout.addWidget(self.custom_input)
            layout.addWidget(self.custom_input_container)

            self.dropdown.currentIndexChanged.connect(self._on_dropdown_changed)
            self._update_custom_input_visibility()

    def _on_dropdown_changed(self):
        self._update_custom_input_visibility()

    def _update_custom_input_visibility(self):
        if self.custom_input_container:
            is_custom = self.dropdown.currentData() == self._CUSTOM_SENTINEL
            self.custom_input_container.setVisible(is_custom)
            if is_custom and self.custom_input:
                self.custom_input.setFocus()

    def set_value(self, value):
        self.internal_value = value

    def get_value(self):
        if self.allow_custom and self.dropdown.currentData() == self._CUSTOM_SENTINEL:
            return self.custom_input.text().strip()
        return self.dropdown.currentData()


class AIProvider(ABC):
    """Abstract base for AI providers (kept even though we only have one,
    so the SettingsWindow provider-picker code keeps working unchanged)."""

    def __init__(self, app, provider_name: str, settings: List[AIProviderSetting],
                 description: str = "An unfinished AI provider!",
                 logo: str = "generic",
                 button_text: str = "Go to URL",
                 button_action: callable = None):
        self.provider_name = provider_name
        self.settings = settings
        self.app = app
        self.description = description if description else "An unfinished AI provider!"
        self.logo = logo
        self.button_text = button_text
        self.button_action = button_action

    @abstractmethod
    def get_response(self, system_instruction: str, prompt: str) -> str:
        pass

    def load_config(self, config: dict):
        for setting in self.settings:
            if setting.name in config:
                setattr(self, setting.name, config[setting.name])
                setting.set_value(config[setting.name])
            else:
                setattr(self, setting.name, setting.default_value)
        self.after_load()

    def save_config(self):
        config = {}
        for setting in self.settings:
            config[setting.name] = setting.get_value()
        self.app.config["providers"][self.provider_name] = config
        self.app.save_config(self.app.config)

    @abstractmethod
    def after_load(self):
        pass

    @abstractmethod
    def before_load(self):
        pass

    @abstractmethod
    def cancel(self):
        pass


class OllamaProvider(AIProvider):
    """
    Connects to an Ollama server and calls the /chat endpoint.
    Non-streaming.
    """

    def __init__(self, app):
        self.close_requested = None
        self.client = None
        self.app = app
        settings = [
            TextSetting("api_base", "API Base URL", "http://192.168.203.100:11434",
                        "E.g. http://192.168.203.100:11434"),
            TextSetting("api_model", "Model", "cogito:32b", "E.g. cogito:32b"),
            TextSetting("keep_alive", "Time to keep the model in memory (minutes)", "5", "E.g. 5"),
        ]
        super().__init__(
            app, "Ollama (For Experts)", settings,
            "• Connects to ACNR's internal Ollama server.",
            "ollama", "Ollama documentation",
            lambda: webbrowser.open("https://github.com/ollama/ollama/blob/main/docs/api.md"),
        )

    def get_response(self, system_instruction: str, prompt, return_response: bool = False) -> str:
        self.close_requested = False

        if isinstance(prompt, list):
            messages = prompt
        else:
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ]

        try:
            response = self.client.chat(model=self.api_model, messages=messages)
            response_text = response["message"]["content"].strip()
            if not return_response and not hasattr(self.app, "current_response_window"):
                self.app.output_ready_signal.emit(response_text)
            return response_text
        except Exception as e:
            logging.error(f"Error during Ollama chat: {e}")
            self.app.output_ready_signal.emit("An error occurred during Ollama chat.")
            return ""

    def after_load(self):
        self.client = OllamaClient(host=self.api_base)

    def before_load(self):
        self.client = None

    def cancel(self):
        self.close_requested = True
