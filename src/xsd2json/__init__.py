"""XSD2JSON: Robust XSD to JSON Schema converter with LLM optimization features."""

__version__ = "0.1.0"
__author__ = "Owen McCusker"
__email__ = "mccuskerowen@gmail.com"

from .converter import Converter
from .config import Config

__all__ = ["Converter", "Config"]
