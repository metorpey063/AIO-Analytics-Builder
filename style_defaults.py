"""Default style configuration for Tableau Next visualizations.

Provides font, line, shading, and encoding builders that produce
API-compliant style objects. Brand colors can be passed as overrides.
"""

from typing import Any, Dict, Optional

STYLE_DEFAULTS: Dict[str, Any] = {
    "backgroundColor": "#FFFFFF",
    "bandingColor": "#E5E5E5",
    "fontColor": "#2E2E2E",
    "fontSize": 13,
    "actionableHeaderColor": "#0250D9",
    "lineColor": "#C9C9C9",
    "fit": None,
}

FONT_KEYS = [
    "actionableHeaders",
    "axisTickLabels",
    "fieldLabels",
    "headers",
    "legendLabels",
    "markLabels",
    "marks",
]

TABLE_EXTRA_FONT_KEYS = ["grandTotalLabel", "grandTotalValues"]

LINE_KEYS = ["axisLine", "fieldLabelDividerLine", "separatorLine", "zeroLine"]

DEFAULT_PALETTE = [
    "#4992fe",
    "#ba01ff",
    "#06a59a",
    "#3a49da",
    "#fe5c4c",
    "#024d4c",
    "#3ba755",
    "#8a033e",
]


def build_fonts(overrides: Dict[str, Any] = None, *, is_table: bool = False) -> dict:
    overrides = overrides or {}
    color = overrides.get("fontColor", STYLE_DEFAULTS["fontColor"])
    size = int(overrides.get("fontSize", STYLE_DEFAULTS["fontSize"]))
    ah_color = overrides.get("actionableHeaderColor", STYLE_DEFAULTS["actionableHeaderColor"])

    fonts = {}
    keys = FONT_KEYS + (TABLE_EXTRA_FONT_KEYS if is_table else [])
    for key in keys:
        fonts[key] = {
            "color": ah_color if key == "actionableHeaders" else color,
            "size": size,
        }
    return fonts


def build_lines(overrides: Dict[str, Any] = None) -> dict:
    overrides = overrides or {}
    color = overrides.get("lineColor", STYLE_DEFAULTS["lineColor"])
    return {k: {"color": color} for k in LINE_KEYS}


def build_shading(overrides: Dict[str, Any] = None, *, with_banding: bool = True) -> dict:
    overrides = overrides or {}
    bg = overrides.get("backgroundColor", STYLE_DEFAULTS["backgroundColor"])
    shading: Dict[str, Any] = {"backgroundColor": bg}
    if with_banding:
        banding_color = overrides.get("bandingColor", STYLE_DEFAULTS["bandingColor"])
        shading["banding"] = {"rows": {"color": banding_color}}
    else:
        shading["banding"] = {}
    return shading


def build_field_labels(overrides: Dict[str, Any] = None, *, is_table: bool = False) -> dict:
    overrides = overrides or {}
    base = {"showDividerLine": False, "showLabels": True}
    if is_table:
        bg = overrides.get("bandingColor", STYLE_DEFAULTS["bandingColor"])
        base["backgroundColor"] = bg
    return {"columns": dict(base), "rows": dict(base)}


def resolve_fit(overrides: Dict[str, Any], chart_default: str) -> str:
    overrides = overrides or {}
    return overrides.get("fit") or chart_default


def num_fmt(fmt_type: str = "Number", decimal_places: int = 2, suffix: str = "", prefix: str = "") -> dict:
    return {
        "decimalPlaces": decimal_places,
        "displayUnits": "Auto",
        "includeThousandSeparator": True if fmt_type in ("Currency", "CurrencyShort", "Number") else False,
        "negativeValuesFormat": "Auto",
        "prefix": prefix,
        "suffix": suffix,
        "type": fmt_type,
    }


def axis_field_entry(fmt_type: str = "Number", decimal_places: int = 2, suffix: str = "", prefix: str = "") -> dict:
    return {
        "isVisible": True,
        "isZeroLineVisible": True,
        "range": {"includeZero": False, "type": "Auto"},
        "scale": {"format": {"numberFormatInfo": num_fmt(fmt_type, decimal_places, suffix, prefix)}},
        "ticks": {"majorTicks": {"type": "Auto"}, "minorTicks": {"type": "Auto"}},
    }


def encoding_field_entry(fmt_type: str = "Number", decimal_places: int = 2, suffix: str = "", prefix: str = "") -> dict:
    return {"defaults": {"format": {"numberFormatInfo": num_fmt(fmt_type, decimal_places, suffix, prefix)}}}


def header_field_entry() -> dict:
    return {"hiddenValues": [], "isVisible": True, "showMissingValues": False}


def marks_headers_style(*, reverse: bool = False) -> dict:
    return {
        "color": {"color": ""},
        "isAutomaticSize": True,
        "label": {
            "canOverlapLabels": False,
            "marksToLabel": {"type": "All"},
            "showMarkLabels": False,
        },
        "range": {"reverse": reverse},
        "size": {"isAutomatic": True, "type": "Pixel", "value": 13},
    }


def marks_panes_style(
    *,
    reverse: bool = False,
    size_type: str = "Pixel",
    size_value: int = 3,
    auto_size: bool = False,
    show_labels: bool = False,
    is_funnel: bool = False,
) -> dict:
    panes = {
        "color": {"color": ""},
        "isAutomaticSize": auto_size,
        "label": {
            "canOverlapLabels": False,
            "marksToLabel": {"type": "All"},
            "showMarkLabels": show_labels,
        },
        "range": {"reverse": reverse},
        "size": {"isAutomatic": auto_size, "type": size_type, "value": size_value},
    }
    if is_funnel:
        panes["isStackingAxisCentered"] = True
        panes["connector"] = {"type": "Origami"}
    else:
        panes["isStackingAxisCentered"] = False
    return panes
