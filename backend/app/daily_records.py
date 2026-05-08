from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .analyzer import parse_window_start
from .corrections import accepted_source_corrections, compact_text, source_key_from_item, youtube_video_id
from .study_packets import (
    duration_seconds_label,
    practice_ledger_videos,
    source_matches,
)


MAX_NOTATION_EVENTS = 96
MAX_RECORDS = 120
MAX_CLIPS_PER_DAY = 5


def video_match_keys(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("sourceKey") or source_key_from_item(item) or "").strip(),
        str(item.get("url") or item.get("sourceUrl") or "").strip(),
        compact_text(item.get("title") or item.get("sourceTitle")),
    }
    video_id = youtube_video_id(item.get("url") or item.get("sourceUrl") or item.get("id"))
    if video_id:
        values.add(video_id.lower())
        values.add(f"youtube:{video_id}")
    return {value for value in values if value}


def item_matches_keys(item: dict[str, Any], keys: set[str]) -> bool:
    if not item or not keys:
        return False
    item_keys = video_match_keys(item)
    signal = " ".join(
        str(item.get(field) or "")
        for field in ("id", "sampleId", "sourceKey", "sourceUrl", "url", "sourceTitle", "title")
    ).lower()
    return bool(item_keys & keys or any(key and key in signal for key in keys))


def sample_duration_seconds(sample: dict[str, Any]) -> int:
    start, end = window_bounds(sample)
    if end > start:
        return end - start
    try:
        return max(0, int(float(sample.get("durationSeconds") or 0)))
    except (TypeError, ValueError):
        return 0


def window_bounds(item: dict[str, Any]) -> tuple[int, int]:
    raw = str(item.get("window") or item.get("sourceWindow") or "")
    start, end = 0, 0
    if "*" in raw:
        try:
            parts = raw.split("*", 1)[1].split("-", 1)
            start = int(float(parts[0]))
            end = int(float(parts[1]))
        except (IndexError, TypeError, ValueError):
            start, end = 0, 0
    if not start:
        try:
            start = int(float(item.get("startSeconds") or item.get("sourceStartSeconds") or 0))
        except (TypeError, ValueError):
            start = 0
    if not end:
        try:
            end = int(float(item.get("endSeconds") or item.get("sourceEndSeconds") or 0))
        except (TypeError, ValueError):
            end = 0
    if end < start:
        end = 0
    return start, end


def source_window_label(start: int, end: int) -> str:
    return f"{start}-{end}" if end > start else ""


def note_duration_kind(seconds: float, tempo_bpm: float) -> str:
    beat_seconds = 60.0 / tempo_bpm if tempo_bpm > 0 else 0.5
    beats = max(0.125, seconds / beat_seconds)
    if beats <= 0.38:
        return "sixteenth"
    if beats <= 0.75:
        return "eighth"
    if beats <= 1.45:
        return "quarter"
    if beats <= 2.6:
        return "half"
    return "whole"


def notation_events(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for transcription in transcriptions:
        notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        tempo = float(transcription.get("tempoBpm") or 0.0)
        source_start = parse_window_start(str(transcription.get("sourceWindow") or ""))
        previous_end = 0.0
        for note in notes:
            if not isinstance(note, dict):
                continue
            start = float(note.get("startSeconds") or 0.0)
            end = float(note.get("endSeconds") or start)
            duration = max(0.0, float(note.get("durationSeconds") or (end - start)))
            if start - previous_end > 0.35:
                rest_seconds = start - previous_end
                events.append(
                    {
                        "kind": "rest",
                        "durationSeconds": round(rest_seconds, 3),
                        "durationKind": note_duration_kind(rest_seconds, tempo),
                        "uncertain": False,
                    }
                )
            note_name = str(note.get("note") or "").strip()
            if not note_name:
                continue
            confidence = float(note.get("confidence") or 0.0)
            events.append(
                {
                    "kind": "note",
                    "note": note_name,
                    "midi": note.get("midi"),
                    "sourceStartSeconds": round(source_start + start, 3),
                    "sourceEndSeconds": round(source_start + end, 3),
                    "durationSeconds": round(duration, 3),
                    "durationKind": note_duration_kind(duration, tempo),
                    "confidence": round(confidence, 3),
                    "uncertain": confidence < 0.62,
                }
            )
            previous_end = max(previous_end, end)
            if len(events) >= MAX_NOTATION_EVENTS:
                return events
    return events


def active_seconds_from_transcriptions(transcriptions: list[dict[str, Any]]) -> int:
    total = 0.0
    for transcription in transcriptions:
        notes = transcription.get("notes") if isinstance(transcription.get("notes"), list) else []
        for note in notes:
            if isinstance(note, dict):
                total += max(0.0, float(note.get("durationSeconds") or 0.0))
    return int(round(total))


def active_seconds_from_sections(sections: list[dict[str, Any]]) -> int:
    total = 0
    seen: set[tuple[str, int, int]] = set()
    for section in sections:
        start, end = window_bounds(section)
        key = (str(section.get("sampleId") or section.get("id") or ""), start, end)
        if end > start and key not in seen:
            total += end - start
            seen.add(key)
    return total


def transcription_fragments(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    durations: dict[str, float] = defaultdict(float)
    examples: dict[str, list[str]] = {}
    for transcription in transcriptions:
        notes = [
            str(note.get("note") or "").strip()
            for note in (transcription.get("notes") if isinstance(transcription.get("notes"), list) else [])
            if isinstance(note, dict) and str(note.get("note") or "").strip()
        ]
        if len(notes) < 4:
            continue
        note_durations = [
            float(note.get("durationSeconds") or 0.0)
            for note in (transcription.get("notes") if isinstance(transcription.get("notes"), list) else [])
            if isinstance(note, dict) and str(note.get("note") or "").strip()
        ]
        for index in range(len(notes) - 3):
            fragment_notes = notes[index : index + 4]
            label = " ".join(fragment_notes)
            counter[label] += 1
            durations[label] += sum(note_durations[index : index + 4])
            examples[label] = fragment_notes
    if not counter:
        return []
    max_count = max(counter.values())
    fragments = []
    for label, count in counter.most_common(8):
        fragments.append(
            {
                "label": label,
                "count": count,
                "seconds": round(durations[label], 1),
                "intensity": round(count / max(1, max_count), 3),
                "notes": examples.get(label, []),
            }
        )
    return fragments


def problem_observations(
    notation: list[dict[str, Any]],
    heat_fragments: list[dict[str, Any]],
    clips: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    active_status: str,
) -> list[dict[str, Any]]:
    primary_clip = clips[0] if clips else {}
    observations: list[dict[str, Any]] = []
    uncertain_notes = Counter(
        str(event.get("note") or "")
        for event in notation
        if event.get("kind") == "note" and event.get("uncertain") and event.get("note")
    )
    if uncertain_notes:
        note, count = uncertain_notes.most_common(1)[0]
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "generated transcription",
                "category": "pitch/rhythm confidence",
                "frequency": f"{count} marked events",
                "trend": "not enough attempts to trend",
                "problem": f"The generated notation marks {note} as uncertain {count} times.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_uncertain_pitch",
                "curtisReadinessIssue": "A repeated uncertain pitch/rhythm location is not stable enough to treat as audition-ready evidence.",
            }
        )

    restart_count = sum(
        1
        for event in notation
        if event.get("kind") == "rest" and float(event.get("durationSeconds") or 0.0) >= 0.65
    )
    if restart_count:
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "generated transcription",
                "category": "consistency",
                "frequency": f"{restart_count} marked pauses",
                "trend": "not enough attempts to trend",
                "problem": f"The transcription contains {restart_count} longer pause or restart markers inside the playing window.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_pause_pattern",
                "curtisReadinessIssue": "Repeated stopping inside a passage means the passage is not yet secure under continuity pressure.",
            }
        )

    if heat_fragments:
        fragment = heat_fragments[0]
        count = int(fragment.get("count") or 0)
        if count >= 2:
            observations.append(
                {
                    "passage": fragment.get("label") or "repeated fragment",
                    "category": "repetition density",
                    "frequency": f"{count} repeats",
                    "trend": "not enough attempts to trend",
                    "problem": f"The fragment {fragment.get('label')} is the densest repeated material in this record.",
                    "evidence": primary_clip,
                    "transcriptionSnippet": notation[:24],
                    "confidence": "machine_observed_repetition",
                    "curtisReadinessIssue": "The day concentrated on this fragment; its stability should be judged from the paired clips before calling it ready.",
                }
            )

    slow_windows = [
        transcription
        for transcription in transcriptions
        if float(transcription.get("tempoBpm") or 0.0) and float(transcription.get("tempoBpm") or 0.0) < 84.0
    ]
    if slow_windows:
        observations.append(
            {
                "passage": heat_fragments[0].get("label") if heat_fragments else "slow transcription window",
                "category": "tempo",
                "frequency": f"{len(slow_windows)} slow windows",
                "trend": "not enough attempts to trend",
                "problem": "At least one transcribed window is marked as slow practice by the tempo estimate.",
                "evidence": primary_clip,
                "transcriptionSnippet": notation[:24],
                "confidence": "machine_observed_tempo",
                "curtisReadinessIssue": "Slow-window evidence is useful, but the passage still needs clean continuity evidence at target tempo.",
            }
        )

    if observations:
        return observations[:4]
    if active_status == "pending_media":
        return [
            {
                "passage": "practice day",
                "category": "media",
                "frequency": "not measured",
                "trend": "pending",
                "problem": "Audio/video has not produced active-playing evidence yet.",
                "evidence": primary_clip,
                "transcriptionSnippet": [],
                "confidence": "pending_media",
                "curtisReadinessIssue": "Curtis cannot make a playing-quality claim until active violin audio is processed.",
            }
        ]
    if not notation:
        return [
            {
                "passage": "active playing window",
                "category": "transcription",
                "frequency": "not measured",
                "trend": "pending",
                "problem": "Active audio exists, but pitch/rhythm notation has not been generated yet.",
                "evidence": primary_clip,
                "transcriptionSnippet": [],
                "confidence": "pending_transcription",
                "curtisReadinessIssue": "Curtis-level observations require notation tied to the exact clip.",
            }
        ]
    return [
        {
            "passage": "generated transcription",
            "category": "observed pattern",
            "frequency": "no repeated failure extracted",
            "trend": "not enough attempts to trend",
            "problem": "No specific repeated pitch, rhythm, pause, or repetition problem was extracted from this notation window.",
            "evidence": primary_clip,
            "transcriptionSnippet": notation[:24],
            "confidence": "machine_observed_no_repeated_problem",
            "curtisReadinessIssue": "This is not a readiness score; it only means the current extraction did not isolate a repeated blocker.",
        }
    ]


def main_curtis_blocker(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "Main Curtis-level blocker pending evidence."
    problem = str(observations[0].get("problem") or "").strip()
    issue = str(observations[0].get("curtisReadinessIssue") or "").strip()
    return " ".join(part for part in (problem, issue) if part)


def heat_map_layers(heat_fragments: list[dict[str, Any]], notation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uncertain_count = sum(1 for event in notation if event.get("kind") == "note" and event.get("uncertain"))
    restart_count = sum(
        1
        for event in notation
        if event.get("kind") == "rest" and float(event.get("durationSeconds") or 0.0) >= 0.65
    )
    problem_items = []
    if uncertain_count:
        problem_items.append({"label": "uncertain notes", "count": uncertain_count, "intensity": min(1.0, uncertain_count / 8)})
    if restart_count:
        problem_items.append({"label": "pause/restart markers", "count": restart_count, "intensity": min(1.0, restart_count / 6)})
    return [
        {
            "label": "Practice density",
            "status": "ready" if heat_fragments else "pending_transcription",
            "items": heat_fragments,
        },
        {
            "label": "Repetition density",
            "status": "ready" if heat_fragments else "pending_transcription",
            "items": heat_fragments,
        },
        {
            "label": "Problem density",
            "status": "ready" if uncertain_count or restart_count else "pending_more_attempts",
            "items": problem_items,
        },
        {
            "label": "Improvement",
            "status": "pending_multiple_aligned_attempts",
            "items": [],
        },
    ]


def clips_for_day(
    videos: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for section in sorted(sections, key=lambda item: float(item.get("meanRms") or 0.0), reverse=True):
        start, end = window_bounds(section)
        if end <= start:
            continue
        clips.append(
            {
                "type": "active_section",
                "label": "audio-active section",
                "url": section.get("url") or "",
                "sourceTitle": section.get("title") or "",
                "startSeconds": start,
                "endSeconds": end,
                "durationSeconds": end - start,
                "reason": section.get("note") or "Audio-active practice section.",
            }
        )
    for transcription in transcriptions:
        start, end = window_bounds(transcription)
        if end <= start:
            continue
        clips.append(
            {
                "type": "transcribed_window",
                "label": "transcribed playing window",
                "url": transcription.get("sourceUrl") or "",
                "sourceTitle": transcription.get("sourceTitle") or "",
                "startSeconds": start,
                "endSeconds": end,
                "durationSeconds": end - start,
                "reason": f"{int(transcription.get('noteCount') or 0)} detected notes.",
            }
        )
    if not clips:
        for video in videos[:2]:
            clips.append(
                {
                    "type": "source_video",
                    "label": "source video",
                    "url": video.get("url") or "",
                    "sourceTitle": video.get("title") or "",
                    "startSeconds": 0,
                    "endSeconds": 0,
                    "durationSeconds": 0,
                    "reason": "Video indexed. Main practice clips pending active-playing detection.",
                }
            )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    for clip in clips:
        key = (
            str(clip.get("url") or ""),
            int(clip.get("startSeconds") or 0),
            int(clip.get("endSeconds") or 0),
            str(clip.get("type") or ""),
        )
        if key not in seen:
            unique.append(clip)
            seen.add(key)
    return unique[:MAX_CLIPS_PER_DAY]


def confirmed_pieces_for_day(
    state: dict[str, Any],
    videos: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    for correction in accepted_source_corrections(state):
        title = str(correction.get("acceptedTitle") or "").strip()
        if not title:
            continue
        matched_video = next((video for video in videos if source_matches(correction, video)), None)
        matched_transcription = next((item for item in transcriptions if source_matches(correction, item)), None)
        if not matched_video and not matched_transcription:
            continue
        source = matched_video or matched_transcription or {}
        pieces.append(
            {
                "title": title,
                "status": "confirmed",
                "confidence": "human_confirmed_source",
                "reason": correction.get("sourceHint") or correction.get("reason") or "Confirmed source label.",
                "sourceTitle": source.get("title") or source.get("sourceTitle") or correction.get("sourceTitle") or "",
                "sourceUrl": source.get("url") or source.get("sourceUrl") or correction.get("sourceUrl") or "",
                "score": correction.get("referenceTarget") if isinstance(correction.get("referenceTarget"), dict) else {},
            }
        )
    return pieces


def uncertain_pieces_for_day(transcriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uncertain: list[dict[str, Any]] = []
    for transcription in transcriptions:
        matches = transcription.get("referenceMatches") if isinstance(transcription.get("referenceMatches"), list) else []
        for match in matches[:2]:
            title = str(match.get("title") or "").strip()
            if not title:
                continue
            uncertain.append(
                {
                    "title": title,
                    "status": "uncertain",
                    "confidence": match.get("score") or 0,
                    "reason": "Pitch/rhythm fingerprint resembles a learned source; score confirmation pending.",
                    "sourceTitle": transcription.get("sourceTitle") or "",
                    "sourceUrl": transcription.get("sourceUrl") or "",
                }
            )
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for item in uncertain:
        key = compact_text(item.get("title"))
        if key and key not in seen:
            clean.append(item)
            seen.add(key)
    return clean


def day_next_step(active_status: str, pieces: list[dict[str, Any]], transcribed: bool) -> str:
    if active_status == "pending_media":
        return "Media processing must finish before active playing, notation, and playing-quality observations can be measured."
    if not transcribed:
        return "Run transcription on the active windows before adding repertoire claims."
    if not pieces:
        return "Keep the transcription as uncertain evidence until it aligns to a known piece or score."
    return "Use the repeated fragments and clips to choose one small passage for the next take."


def day_summary(active_status: str, pieces: list[dict[str, Any]], uncertain: list[dict[str, Any]]) -> str:
    if pieces:
        return "Confirmed repertoire evidence recorded for this practice day."
    if uncertain:
        return "Possible repertoire evidence exists, but it is not confirmed."
    if active_status == "pending_media":
        return "Video metadata is indexed; audio/video processing has not produced active-playing evidence yet."
    return "Practice evidence processed; piece confirmation pending."


def build_daily_records(
    state: dict[str, Any],
    inventory: dict[str, list[dict[str, Any]]],
    media_samples: list[dict[str, Any]],
    transcriptions: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger = practice_ledger_videos(inventory)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for video in ledger:
        day = str(video.get("practiceDay") or video.get("uploadedDate") or "")
        if day:
            grouped[day].append(video)

    records: list[dict[str, Any]] = []
    for day, videos in grouped.items():
        keys = set().union(*(video_match_keys(video) for video in videos))
        day_samples = [sample for sample in media_samples if item_matches_keys(sample, keys)]
        day_transcriptions = [item for item in transcriptions if item_matches_keys(item, keys)]
        day_sections = [
            section
            for section in sections
            if item_matches_keys(section, keys)
            or any(str(section.get("sampleId") or "") == str(sample.get("id") or "") for sample in day_samples)
        ]
        notation = notation_events(day_transcriptions)
        note_active = active_seconds_from_transcriptions(day_transcriptions)
        section_active = active_seconds_from_sections(day_sections)
        active_seconds = note_active or section_active
        active_status = (
            "measured_from_pitch"
            if note_active
            else "estimated_from_audio_energy"
            if section_active
            else "pending_media"
        )
        confirmed = confirmed_pieces_for_day(state, videos, day_transcriptions)
        uncertain = uncertain_pieces_for_day(day_transcriptions)
        heat_fragments = transcription_fragments(day_transcriptions)
        uploaded_seconds = sum(int(video.get("durationSeconds") or 0) for video in videos)
        processed_seconds = sum(sample_duration_seconds(sample) for sample in day_samples)
        clips = clips_for_day(videos, day_sections, day_transcriptions)
        observations = problem_observations(notation, heat_fragments, clips, day_transcriptions, active_status)
        blocker = main_curtis_blocker(observations)
        records.append(
            {
                "practiceDay": day,
                "status": "transcribed" if notation else "active_time_measured" if active_seconds else "pending_media",
                "videos": videos,
                "videoCount": len(videos),
                "uploadedVideoSeconds": uploaded_seconds,
                "uploadedVideoLabel": duration_seconds_label(uploaded_seconds),
                "processedSampleSeconds": processed_seconds,
                "processedSampleLabel": duration_seconds_label(processed_seconds) if processed_seconds else "",
                "activeViolinSeconds": active_seconds,
                "activeViolinLabel": duration_seconds_label(active_seconds) if active_seconds else "",
                "activeTimeStatus": active_status,
                "pieces": confirmed,
                "uncertainPieces": uncertain,
                "transcription": {
                    "status": "ready" if notation else "pending",
                    "noteCount": sum(int(item.get("noteCount") or 0) for item in day_transcriptions),
                    "segmentCount": len(day_transcriptions),
                    "events": notation,
                    "limit": "Machine notation from detected monophonic violin pitch/rhythm; uncertain notes are marked.",
                },
                "clips": clips,
                "heatMap": {
                    "status": "ready" if heat_fragments else "pending_transcription",
                    "fragments": heat_fragments,
                    "layers": heat_map_layers(heat_fragments, notation),
                    "limit": "Heat map currently uses repeated four-note fragments from machine transcription.",
                },
                "observations": observations,
                "mainCurtisBlocker": blocker,
                "repertoireUpdates": [
                    {
                        "pieceTitle": item["title"],
                        "action": "add_or_update",
                        "status": "confirmed",
                        "reason": item.get("reason") or "Confirmed source evidence.",
                    }
                    for item in confirmed
                ],
                "evidenceStatus": "confirmed_piece" if confirmed else "uncertain_piece" if uncertain else active_status,
                "summary": day_summary(active_status, confirmed, uncertain),
                "nextStep": day_next_step(active_status, confirmed, bool(notation)),
            }
        )

    records.sort(key=lambda item: str(item.get("practiceDay") or ""), reverse=True)
    total_uploaded = sum(int(record.get("uploadedVideoSeconds") or 0) for record in records)
    total_active = sum(int(record.get("activeViolinSeconds") or 0) for record in records)
    return {
        "status": "ready" if records else "pending",
        "recordCount": len(records),
        "totalUploadedVideoSeconds": total_uploaded,
        "totalUploadedVideoLabel": duration_seconds_label(total_uploaded),
        "totalActiveViolinSeconds": total_active,
        "totalActiveViolinLabel": duration_seconds_label(total_active) if total_active else "",
        "transcribedRecordCount": sum(1 for record in records if record.get("transcription", {}).get("status") == "ready"),
        "records": records[:MAX_RECORDS],
        "method": "Groups title-confirmed practice videos by practice day, then attaches uploaded duration, active-time evidence, machine notation, clips, heat-map fragments, and repertoire evidence.",
        "limit": "Records without fetched/uploaded media stay pending; the app does not invent active violin time, notation, clips, or repertoire labels.",
    }


def build_repertoire_evidence(daily_records: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    for record in daily_records.get("records", []):
        if not isinstance(record, dict):
            continue
        for piece in record.get("pieces", []):
            if not isinstance(piece, dict):
                continue
            title = str(piece.get("title") or "").strip()
            key = compact_text(title)
            if not key:
                continue
            entry = entries.setdefault(
                key,
                {
                    "title": title,
                    "status": "confirmed",
                    "reason": piece.get("reason") or "Confirmed source evidence.",
                    "totalActiveViolinSeconds": 0,
                    "totalUploadedVideoSeconds": 0,
                    "recentPracticeDays": [],
                    "evidence": [],
                    "observations": [],
                },
            )
            entry["totalActiveViolinSeconds"] += int(record.get("activeViolinSeconds") or 0)
            entry["totalUploadedVideoSeconds"] += int(record.get("uploadedVideoSeconds") or 0)
            entry["recentPracticeDays"].append(record.get("practiceDay"))
            clip = (record.get("clips") or [{}])[0] if isinstance(record.get("clips"), list) else {}
            notation_events_for_record = record.get("transcription", {}).get("events", [])
            entry["evidence"].append(
                {
                    "practiceDay": record.get("practiceDay"),
                    "clip": clip,
                    "transcriptionSnippet": notation_events_for_record[:24] if isinstance(notation_events_for_record, list) else [],
                    "score": piece.get("score") or {},
                    "reason": piece.get("reason") or "Confirmed source evidence.",
                    "confidence": piece.get("confidence") or "confirmed",
                }
            )
            for observation in record.get("observations", [])[:2]:
                if isinstance(observation, dict):
                    entry["observations"].append(
                        {
                            "practiceDay": record.get("practiceDay"),
                            "passage": observation.get("passage"),
                            "category": observation.get("category"),
                            "problem": observation.get("problem"),
                            "frequency": observation.get("frequency"),
                            "trend": observation.get("trend"),
                            "curtisReadinessIssue": observation.get("curtisReadinessIssue"),
                            "confidence": observation.get("confidence"),
                        }
                    )
    output = []
    for entry in entries.values():
        days = [str(day) for day in entry["recentPracticeDays"] if day]
        entry["recentPracticeDays"] = list(dict.fromkeys(days))[:8]
        entry["totalActiveViolinLabel"] = duration_seconds_label(entry["totalActiveViolinSeconds"]) if entry["totalActiveViolinSeconds"] else ""
        entry["totalUploadedVideoLabel"] = duration_seconds_label(entry["totalUploadedVideoSeconds"])
        entry["progressStatus"] = "not_scored"
        entry["currentProgressLabel"] = "not scored"
        entry["mainCurtisBlocker"] = (
            str(entry["observations"][0].get("curtisReadinessIssue") or entry["observations"][0].get("problem") or "")
            if entry["observations"]
            else "Specific blocker pending aligned transcription evidence."
        )
        entry["nextStep"] = "Progress percentage stays unassigned until clips, notation, and score alignment support it."
        output.append(entry)
    output.sort(key=lambda item: (len(item.get("recentPracticeDays", [])), item.get("title", "")), reverse=True)
    return {
        "status": "ready" if output else "pending",
        "entryCount": len(output),
        "entries": output,
        "method": "Only confirmed daily-record evidence promotes repertoire entries.",
        "limit": "Uncertain piece matches remain daily evidence and do not become repertoire entries.",
    }
