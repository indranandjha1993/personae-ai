"""Audio-derived mouth shapes are validated and mapped to canonical channels."""

import asyncio
from pathlib import Path

import pytest

from personae.lip_alignment import parse_rhubarb


def test_maps_closed_lips_and_open_vowels() -> None:
    cues = parse_rhubarb(
        {
            "mouthCues": [
                {"start": 0, "end": 0.1, "value": "A"},
                {"start": 0.1, "end": 0.4, "value": "D"},
            ]
        }
    )
    assert [cue.value for cue in cues] == ["closed", "aa"]
    assert cues[1].start == 0.1


def test_rejects_unknown_mouth_shape() -> None:
    with pytest.raises(ValueError, match="literal"):
        parse_rhubarb({"mouthCues": [{"start": 0, "end": 1, "value": "invalid"}]})


async def test_analyzer_invocation_writes_pcm_and_cleans_files(tmp_path: Path) -> None:
    import sys

    from personae.lip_alignment import Rhubarb

    executable = tmp_path / "rhubarb-stub"
    record = tmp_path / "input-path"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys, wave\n"
        "source = pathlib.Path(sys.argv[-1])\n"
        f"pathlib.Path({str(record)!r}).write_text(str(source))\n"
        "with wave.open(str(source)) as audio:\n"
        "    assert audio.getframerate() == 24000\n"
        "    assert audio.getsampwidth() == 2\n"
        "    assert audio.getnchannels() == 1\n"
        '    assert audio.readframes(2) == b"\\x01\\x00\\x02\\x00"\n'
        'print(json.dumps({"mouthCues": [{"start": 0, "end": 0.01, "value": "D"}]}))\n',
        encoding="utf-8",
    )
    executable.chmod(0o700)
    cues = await Rhubarb(str(executable)).analyze(b"\x01\x00\x02\x00", "Hello")
    assert cues[0].value == "aa"
    assert not await asyncio.to_thread(Path(record.read_text()).exists)


async def test_cancelled_analysis_terminates_process(tmp_path: Path) -> None:
    import os
    import sys

    from personae.lip_alignment import Rhubarb

    executable = tmp_path / "rhubarb-stub"
    record = tmp_path / "pid"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, time\n"
        f"pathlib.Path({str(record)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    task = asyncio.create_task(Rhubarb(str(executable)).analyze(b"\x00\x00", "Hi"))
    try:
        async with asyncio.timeout(3):
            while not record.exists():  # noqa: ASYNC110 - child process readiness file
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(record.read_text()), 0)
