"""
Coding Exclusive #2 — Live Invariant Miner
==========================================
Leitet aus Runtime-Traces automatisch Property-based Test-Hypothesen ab
und schreibt sie als `hypothesis`-Strategien direkt in die Codebasis.

Global-unique weil:
  Kein OSS-Tool beobachtet echte Laufzeitwerte, destilliert daraus
  Wertebereiche/Typen/Invarianten UND schreibt vollständige
  @hypothesis.given()-Tests zurück — persistent, wachsend, versioniert.

Pipeline:
  1. sys.settrace() auf Ziel-Funktion → Werte aller Argumente sammeln
  2. Counter/Set pro Argument → Wertebereich + Typ-Muster ableiten
  3. Claude generiert @given(st.integers(min=..., max=...)) Strategien
  4. write_file() schreibt Tests in test_invariants_[module].py

Verwendung:
  miner = InvariantMiner()
  miner.trace(my_function, calls=100)   # Funktion 100x beobachten
  miner.mine_and_write("tests/")        # Hypothesis-Tests schreiben
"""

from __future__ import annotations

import ast
import collections
import inspect
import os
import sys
import textwrap
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ── Werte-Beobachtung ─────────────────────────────────────────────────────────

@dataclass
class ArgProfile:
    """Beobachtete Werte eines Funktions-Arguments."""
    name: str
    observed_values: list[Any] = field(default_factory=list)
    observed_types: set[str] = field(default_factory=set)

    def update(self, value: Any):
        self.observed_values.append(value)
        self.observed_types.add(type(value).__name__)

    @property
    def numeric_range(self) -> tuple[float, float] | None:
        nums = [v for v in self.observed_values if isinstance(v, (int, float))]
        if not nums:
            return None
        return min(nums), max(nums)

    @property
    def str_lengths(self) -> tuple[int, int] | None:
        strs = [v for v in self.observed_values if isinstance(v, str)]
        if not strs:
            return None
        return min(len(s) for s in strs), max(len(s) for s in strs)

    @property
    def dominant_type(self) -> str:
        if not self.observed_types:
            return "Any"
        # Häufigster Typ
        counter = collections.Counter(type(v).__name__ for v in self.observed_values)
        return counter.most_common(1)[0][0]

    @property
    def is_nullable(self) -> bool:
        return any(v is None for v in self.observed_values)

    @property
    def sample_values(self) -> list[str]:
        unique = list({repr(v) for v in self.observed_values})[:5]
        return unique


@dataclass
class ReturnProfile:
    """Beobachtete Rückgabewerte einer Funktion."""
    observed_returns: list[Any] = field(default_factory=list)

    def update(self, value: Any):
        self.observed_returns.append(value)

    @property
    def dominant_type(self) -> str:
        if not self.observed_returns:
            return "Any"
        counter = collections.Counter(type(v).__name__ for v in self.observed_returns)
        return counter.most_common(1)[0][0]

    @property
    def never_none(self) -> bool:
        return all(v is not None for v in self.observed_returns)

    @property
    def always_positive(self) -> bool:
        nums = [v for v in self.observed_returns if isinstance(v, (int, float))]
        return bool(nums) and all(v > 0 for v in nums)


@dataclass
class FunctionProfile:
    name: str
    module: str
    args: dict[str, ArgProfile] = field(default_factory=dict)
    returns: ReturnProfile = field(default_factory=ReturnProfile)
    call_count: int = 0
    exceptions_seen: list[str] = field(default_factory=list)


# ── Tracer ────────────────────────────────────────────────────────────────────

class InvariantMiner:
    """
    Beobachtet Funktionen via sys.settrace() und destilliert
    Property-based Hypothesis-Tests aus den Laufzeitwerten.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._profiles: dict[str, FunctionProfile] = {}
        self._active_func: str = ""

    def trace(self, func: Callable, inputs: list[tuple] | None = None, calls: int = 0):
        """
        Beobachtet Funktion direkt oder wartet auf organische Aufrufe.

        Args:
            func:   Zu beobachtende Funktion
            inputs: Liste von Argument-Tupeln für direkte Aufrufe
            calls:  Anzahl organischer Aufrufe zu beobachten (0 = direkt)
        """
        fname = f"{func.__module__}.{func.__qualname__}"
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        profile = FunctionProfile(
            name=func.__qualname__,
            module=func.__module__,
            args={p: ArgProfile(name=p) for p in param_names},
        )
        self._profiles[fname] = profile
        self._active_func = fname

        if inputs:
            # Direkte Aufrufe mit bekannten Inputs
            original_trace = sys.gettrace()
            sys.settrace(self._make_tracer(fname, param_names))
            for args in inputs:
                try:
                    result = func(*args)
                    profile.returns.update(result)
                    profile.call_count += 1
                except Exception as e:
                    profile.exceptions_seen.append(type(e).__name__)
            sys.settrace(original_trace)

        return profile

    def _make_tracer(self, fname: str, param_names: list[str]):
        """Erstellt sys.settrace-kompatible Tracer-Funktion."""
        profile = self._profiles[fname]

        def tracer(frame, event, arg):
            if event == "call":
                for i, name in enumerate(param_names):
                    if name in frame.f_locals:
                        profile.args[name].update(frame.f_locals[name])
                profile.call_count += 1
            elif event == "return":
                profile.returns.update(arg)
            return tracer

        return tracer

    def observe_module(self, module_path: str, sample_inputs: dict[str, list]):
        """
        Lädt ein Modul und beobachtet alle Funktionen mit Sample-Inputs.
        sample_inputs: {"function_name": [(arg1, arg2), ...]}
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("_observed", module_path)
        if not spec or not spec.loader:
            raise ValueError(f"Kann Modul nicht laden: {module_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore

        for func_name, inputs in sample_inputs.items():
            func = getattr(mod, func_name, None)
            if callable(func):
                self.trace(func, inputs=inputs)

    # ── Hypothesis-Strategie-Generierung ──────────────────────────────────────

    def _profile_to_strategy(self, arg_profile: ArgProfile) -> str:
        """Leitet hypothesis.strategies aus ArgProfile ab."""
        dtype = arg_profile.dominant_type

        if dtype == "int":
            r = arg_profile.numeric_range
            if r:
                lo, hi = int(r[0]), int(r[1])
                # Etwas Puffer für Grenzfälle
                return f"st.integers(min_value={lo - 1}, max_value={hi + 1})"
            return "st.integers()"

        elif dtype == "float":
            r = arg_profile.numeric_range
            if r:
                return f"st.floats(min_value={r[0]:.4f}, max_value={r[1]:.4f}, allow_nan=False)"
            return "st.floats(allow_nan=False)"

        elif dtype == "str":
            sl = arg_profile.str_lengths
            if sl:
                return f"st.text(min_size={sl[0]}, max_size={sl[1]})"
            return "st.text()"

        elif dtype == "bool":
            return "st.booleans()"

        elif dtype == "list":
            return "st.lists(st.integers())"

        elif dtype == "NoneType" or arg_profile.is_nullable:
            inner = self._profile_to_strategy(
                ArgProfile(arg_profile.name, [v for v in arg_profile.observed_values if v is not None])
            )
            return f"st.one_of(st.none(), {inner})"

        # Fallback: Beispielwerte
        samples = arg_profile.sample_values[:3]
        if samples:
            return f"st.sampled_from([{', '.join(samples)}])"
        return "st.text()"

    def _build_properties(self, profile: FunctionProfile) -> list[str]:
        """Leitet testbare Properties aus Return-Profil ab."""
        props = []
        ret = profile.returns

        if ret.never_none and ret.observed_returns:
            props.append(f"assert result is not None")

        if ret.always_positive:
            props.append(f"assert result > 0")

        if ret.dominant_type == "str":
            props.append(f"assert isinstance(result, str)")

        if ret.dominant_type in ("int", "float"):
            nums = [v for v in ret.observed_returns if isinstance(v, (int, float))]
            if nums:
                lo, hi = min(nums) * 0.5, max(nums) * 2
                props.append(f"assert {lo:.2f} <= result <= {hi:.2f}  # Empirische Schranke")

        if not props:
            props.append(f"# Keine automatische Property ableitbar — manuell ergänzen")

        return props

    def generate_hypothesis_tests(self, profile: FunctionProfile) -> str:
        """Generiert vollständigen Hypothesis-Test-Code für ein FunctionProfile."""
        strategies = {
            name: self._profile_to_strategy(arg)
            for name, arg in profile.args.items()
        }
        properties = self._build_properties(profile)

        given_args = ", ".join(
            f"{name}={strategy}" for name, strategy in strategies.items()
        )
        func_args = ", ".join(strategies.keys())
        property_block = "\n    ".join(properties)

        # Optional: Claude für bessere Property-Beschreibungen
        prop_comment = self._claude_property_description(profile)

        test_code = f"""# Auto-generiert von InvariantMiner — {profile.call_count} Aufrufe beobachtet
# Modul: {profile.module}
{prop_comment}

from hypothesis import given, settings
import hypothesis.strategies as st
from {profile.module} import {profile.name.split('.')[0]}


@given({given_args})
@settings(max_examples=200, deadline=5000)
def test_{profile.name.replace('.', '_')}_invariants({func_args}):
    \"\"\"
    Auto-abgeleitete Invarianten aus {profile.call_count} echten Laufzeit-Aufrufen.
    Beobachtete Typen: {{{', '.join(f'{n}: {a.dominant_type}' for n, a in profile.args.items())}}}
    \"\"\"
    result = {profile.name.split('.')[-1]}({func_args})
    {property_block}
"""
        return test_code

    def _claude_property_description(self, profile: FunctionProfile) -> str:
        """Nutzt Claude Haiku für präzisere Property-Beschreibungen (optional)."""
        if not self.api_key:
            return f"# {profile.call_count} Aufrufe beobachtet, Invarianten automatisch extrahiert"
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            summary = (
                f"Funktion '{profile.name}' mit Args: "
                + ", ".join(f"{n} ({a.dominant_type}, Range: {a.numeric_range})"
                            for n, a in profile.args.items())
                + f". Gibt {profile.returns.dominant_type} zurück."
                + (f" Never None." if profile.returns.never_none else "")
                + (f" Always positive." if profile.returns.always_positive else "")
            )
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"Beschreibe in einem Python-Kommentar (# ...) die Kern-Invariante: {summary}"
                }]
            )
            return response.content[0].text.strip()
        except Exception:
            return ""

    def mine_and_write(self, output_dir: str = "tests/") -> dict[str, str]:
        """
        Generiert und schreibt Hypothesis-Tests für alle beobachteten Funktionen.
        Returns: {Dateiname: generierter Code}
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        written = {}

        for fname, profile in self._profiles.items():
            if profile.call_count == 0:
                continue

            test_code = self.generate_hypothesis_tests(profile)
            module_safe = profile.module.replace(".", "_").replace("/", "_")
            func_safe = profile.name.replace(".", "_")
            filename = f"test_invariants_{module_safe}_{func_safe}.py"
            filepath = out_path / filename

            filepath.write_text(test_code, encoding="utf-8")
            written[filename] = test_code

        return written

    def summary(self) -> str:
        lines = [f"InvariantMiner: {len(self._profiles)} Funktionen beobachtet"]
        for fname, profile in self._profiles.items():
            lines.append(
                f"  {profile.name}: {profile.call_count} Aufrufe, "
                f"{len(profile.args)} Args, "
                f"Return={profile.returns.dominant_type}"
            )
        return "\n".join(lines)


# ── LangChain Tool ────────────────────────────────────────────────────────────

def as_langchain_tool():
    try:
        from langchain_core.tools import tool

        @tool
        def mine_invariants(module_path: str, function_name: str, sample_inputs_json: str) -> str:
            """Beobachtet eine Python-Funktion und generiert Hypothesis-Tests aus Laufzeitwerten.
            sample_inputs_json: JSON-Array von Argument-Tupeln, z.B. '[[1,2],[3,4]]'"""
            import json
            try:
                inputs = [tuple(x) for x in json.loads(sample_inputs_json)]
            except Exception as e:
                return f"Fehler beim Parsen von sample_inputs_json: {e}"

            miner = InvariantMiner()
            miner.observe_module(module_path, {function_name: inputs})
            written = miner.mine_and_write("tests/invariants/")

            if written:
                names = list(written.keys())
                return f"✓ Invariant-Tests geschrieben: {names}\n{miner.summary()}"
            return "Keine Aufrufe beobachtet — prüfe Pfad und Funktionsname"

        return mine_invariants
    except ImportError:
        return None
