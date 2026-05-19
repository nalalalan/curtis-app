from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .state import utc_now


FIVE_ONE_KEY = "youtube:wDfVpTU4I_I"
FIVE_ONE_ACCEPTED_TITLE = "Haydn Symphony No. 94, IV. Finale, Violin I part"
FIVE_TWO_KEY = "youtube:K38CgZhvF3Q"
FIVE_TWO_ACCEPTED_TITLE = "Wieniawski Scherzo-Tarantelle, Op. 16"
FIVE_THREE_KEY = "title:5 3 26"
FIVE_ONE_REJECTED_TITLES = [
    "Paganini",
    "Paganini Violin Concerto No. 1",
    "Paganini Violin Concerto No. 1 in D major, Op. 6",
    "Paganini Caprice No. 5",
    "Paganini Caprice No. 24",
    "Bruch",
    "Max Bruch",
    "Bruch Violin Concerto No. 1",
    "Bruch Violin Concerto No. 1 in G minor, Op. 26",
    "Max Bruch Violin Concerto No. 1 in G minor, Op. 26",
    "Mendelssohn",
    "Felix Mendelssohn",
    "Mendelssohn Violin Concerto",
    "Mendelssohn Violin Concerto in E minor, Op. 64",
    "Felix Mendelssohn Violin Concerto in E minor, Op. 64",
    "Brahms",
    "Johannes Brahms",
    "Brahms Hungarian Dance No. 5",
    "Brahms Hungarian Dance No. 5 (arranged for violin)",
    "Hungarian Dance No. 5",
    "Sibelius",
    "Jean Sibelius",
    "Sibelius Violin Concerto",
    "Sibelius Violin Concerto in D minor, Op. 47",
    "Sibelius Violin Concerto in D minor, Op. 47, 3rd movement",
    "Jean Sibelius Violin Concerto in D minor, Op. 47, 3rd movement",
    "Tchaikovsky",
    "Pyotr Ilyich Tchaikovsky",
    "Tchaikovsky Violin Concerto",
    "Tchaikovsky Violin Concerto in D major, Op. 35",
    "Tchaikovsky Violin Concerto in D major, Op. 35, 3rd movement",
    "Pyotr Ilyich Tchaikovsky Violin Concerto in D major, Op. 35, 3rd movement",
    "Wieniawski",
    "Wieniawski Violin Concerto No. 2",
    "Wieniawski Polonaise Brillante No. 1 in D major, Op. 4",
    "Wieniawski Scherzo-Tarantelle, Op. 16",
    "Saint-Saens",
    "Saint-Saens Introduction and Rondo Capriccioso, Op. 28",
    "Ravel",
    "Ravel Tzigane",
    "Tzigane",
    "Bazzini",
    "Bazzini La Ronde des Lutins, Op. 25",
    "La Ronde des Lutins",
    "Ernst",
    "Ernst Last Rose of Summer Variations",
    "The Last Rose of Summer",
    "Ernst Grand Caprice on Schubert's Erlkonig",
    "Erlkonig",
    "Sarasate",
    "Pablo de Sarasate",
    "Sarasate Introduction and Tarantella",
    "Pablo de Sarasate Introduction and Tarantella, Op. 43",
    "Sarasate Caprice Basque",
    "Pablo de Sarasate Caprice Basque, Op. 24",
    "Pablo de Sarasate Carmen Fantasy, Op. 25",
    "Sarasate Carmen Fantasy",
    "Carmen Fantasy",
    "Pablo de Sarasate Zigeunerweisen, Op. 20",
    "Sarasate Zigeunerweisen",
    "Zigeunerweisen",
    "Bach",
    "J.S. Bach",
    "Johann Sebastian Bach",
    "J.S. Bach Partita No. 2 in D minor, BWV 1004",
    "J.S. Bach Violin Partita No. 2 in D minor, BWV 1004",
    "Johann Sebastian Bach Violin Partita No. 2 in D minor, BWV 1004",
    "Bach Partita No. 2",
    "Bach Partita No. 2 in D minor, BWV 1004",
    "J.S. Bach Partita No. 3 in E major, BWV 1006",
    "J.S. Bach Violin Partita No. 3 in E major, BWV 1006",
    "J.S. Bach Partita No. 3 in E major, BWV 1006, Preludio",
    "Johann Sebastian Bach Violin Partita No. 3 in E major, BWV 1006",
    "Bach Partita No. 3",
    "Bach Partita No. 3 in E major, BWV 1006",
    "Bach Partita No. 3 Preludio",
    "Kreisler Praeludium and Allegro",
    "Fritz Kreisler Praeludium and Allegro",
    "Praeludium and Allegro",
    "Praeludium and Allegro in the Style of Pugnani",
    "Sarasate Zapateado",
    "Sarasate Zapateado Op. 23 No. 2",
    "Pablo de Sarasate Zapateado, Op. 23 No. 2",
    "Zapateado",
    "Ysaye Sonata No. 3 Ballade",
    "Ysaÿe Sonata No. 3 Ballade",
    "Eugene Ysaye Sonata No. 3 Ballade",
    "Eugène Ysaÿe Sonata No. 3 Ballade",
    "Ysaÿe Solo Violin Sonata No. 3, Op. 27 No. 3, Ballade",
    "Ysaye Solo Violin Sonata No. 3, Op. 27 No. 3, Ballade",
    "Mozart",
    "Wolfgang Amadeus Mozart",
    "Mozart K. 216",
    "Mozart Violin Concerto No. 3",
    "Mozart Violin Concerto No. 3 in G major, K. 216",
    "Mozart Violin Concerto No. 3 in G major, K. 216, 3rd movement",
    "Wolfgang Amadeus Mozart Violin Concerto No. 3 in G major, K. 216",
    "Mikhail Glinka Ruslan and Lyudmila Overture",
    "Glinka Ruslan and Lyudmila Overture",
    "Ruslan and Lyudmila Overture",
    "Richard Strauss Till Eulenspiegel's Merry Pranks",
    "Till Eulenspiegel's Merry Pranks",
    "Richard Strauss Don Juan",
    "Smetana The Bartered Bride Overture",
    "The Bartered Bride Overture",
    "Prokofiev Classical Symphony",
    "Dvorak Carnival Overture",
    "Shostakovich Symphony No. 5",
    "Ravel Bolero",
    "Bolero",
    "Beethoven Symphony No. 9, Scherzo, Violin I part",
    "Beethoven Symphony No. 7, fourth movement, Violin I part",
    "Beethoven Leonore Overture No. 3, Violin I part",
    "Schumann Symphony No. 2, Scherzo, Violin I part",
    "Schubert Symphony No. 9, fourth movement, Violin I part",
    "Rossini William Tell Overture, finale, Violin I part",
    "Rossini Semiramide Overture, Violin I part",
    "Rossini La Gazza Ladra Overture, Violin I part",
    "Weber Der Freischutz Overture, Violin I part",
    "Weber Oberon Overture, Violin I part",
    "Berlioz Roman Carnival Overture, Violin I part",
    "Berlioz Symphonie fantastique, fifth movement, Violin I part",
    "Wagner Tannhauser Overture, Violin I part",
    "Wagner Die Meistersinger von Nurnberg Overture, Violin I part",
    "Wagner Rienzi Overture, Violin I part",
    "Verdi La Forza del Destino Overture, Violin I part",
    "Verdi Nabucco Overture, Violin I part",
    "Smetana The Moldau, Violin I part",
    "Rimsky-Korsakov Scheherazade, Violin I part",
    "Rimsky-Korsakov Capriccio Espagnol, Violin I part",
    "Borodin Polovtsian Dances, Violin I part",
    "Bizet L'Arlesienne Suite No. 2, Farandole, Violin I part",
    "Mahler Symphony No. 1, fourth movement, Violin I part",
    "Mahler Symphony No. 5, Scherzo, Violin I part",
    "Mahler Symphony No. 9, first movement, Violin I part",
    "Prokofiev Romeo and Juliet, Violin I part",
    "Prokofiev Lieutenant Kije Suite, Violin I part",
    "Dvorak Symphony No. 9, Scherzo, Violin I part",
    "Dvorak Slavonic Dances, Violin I part",
    "Shostakovich Symphony No. 10, Scherzo, Violin I part",
    "Shostakovich Festive Overture, Violin I part",
    "Nielsen Maskarade Overture, Violin I part",
    "Elgar Cockaigne Overture, Violin I part",
    "Stravinsky Firebird Suite, Violin I part",
    "Stravinsky Petrushka, Violin I part",
    "Stravinsky The Rite of Spring, Violin I part",
    "Bartok Concerto for Orchestra, Violin I part",
    "Kodaly Dances of Galanta, Violin I part",
    "Khachaturian Sabre Dance, Violin I part",
    "Holst The Planets, Mercury, Violin I part",
    "Rossini The Barber of Seville Overture, Violin I part",
    "Rossini L'italiana in Algeri Overture, Violin I part",
    "Rossini La Scala di Seta Overture, Violin I part",
    "Beethoven Symphony No. 5, Scherzo or finale, Violin I part",
    "Beethoven Symphony No. 3, Scherzo, Violin I part",
    "Beethoven Egmont Overture, Violin I part",
    "Weber Euryanthe Overture, Violin I part",
    "Auber Fra Diavolo Overture, Violin I part",
    "Suppe Poet and Peasant Overture, Violin I part",
    "Suppe Light Cavalry Overture, Violin I part",
    "Offenbach Orpheus in the Underworld Overture, Violin I part",
    "Johann Strauss II Die Fledermaus Overture, Violin I part",
    "Johann Strauss II Tritsch-Tratsch Polka, Violin I part",
    "Johann Strauss II Perpetuum Mobile, Violin I part",
    "Johann Strauss II Thunder and Lightning Polka, Violin I part",
    "Josef Strauss Feuerfest Polka, Violin I part",
    "Glinka Kamarinskaya, Violin I part",
    "Rimsky-Korsakov Russian Easter Overture, Violin I part",
    "Rimsky-Korsakov The Tsar's Bride Overture, Violin I part",
    "Borodin Symphony No. 2, Violin I part",
    "Mussorgsky Night on Bald Mountain, Violin I part",
    "Grieg Holberg Suite, Praeludium, Violin I part",
    "Grieg Peer Gynt, In the Hall of the Mountain King, Violin I part",
    "Copland Rodeo, Hoe-Down, Violin I part",
    "Copland El Salon Mexico, Violin I part",
    "Bernstein Candide Overture, Violin I part",
    "Bernstein West Side Story, Mambo, Violin I part",
    "Bernstein West Side Story, America, Violin I part",
    "Arturo Marquez Danzon No. 2, Violin I part",
    "Moncayo Huapango, Violin I part",
    "Ginastera Estancia, Malambo, Violin I part",
    "Revueltas Sensemaya, Violin I part",
    "Gershwin Cuban Overture, Violin I part",
    "Gershwin An American in Paris, Violin I part",
    "John Adams Short Ride in a Fast Machine, Violin I part",
    "John Williams Star Wars Main Title, Violin I part",
    "John Williams Raiders March, Violin I part",
]
SOURCE_ACCEPTANCE_REJECT_COUNT = 3
BUILTIN_CORRECTION_KEYS = [FIVE_ONE_KEY, FIVE_TWO_KEY, FIVE_THREE_KEY]
WIENIAWSKI_REFERENCE_AUDIO_PITCH_CLASSES = (
    "D D D D D D# G G D D G G D D D A# A# A# A# F A A E G "
    "G A# A# A# A# A G D# D# D# F# G G G G C# B A# A# A# A# A# A# A# "
    "A# A# A# D D D D D D D D D D D D D D D D D D D D D "
    "D D A# D D D D# A A# A# F A A A E E A A E F F F G G "
    "G F A# A G D# D# G G G G G G G B B B B B B B B D D "
    "D D D D D D D D D D D D D D D# D# D D D D# D D A# G "
    "D D G G D D D D D D G B B B B B D G C C C C D C "
    "G A A D D F# D A G A D"
).split()


def compact_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def youtube_video_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{6,})", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", text.strip()):
        return text.strip()
    return ""


def title_has_practice_date(title_key: str, month: int, day: int) -> bool:
    return bool(re.search(rf"\b0?{month} 0?{day} (?:26|2026)\b", title_key))


def source_key(*, url: Any = "", title: Any = "", sample_id: Any = "", video_id: Any = "") -> str:
    direct_id = youtube_video_id(video_id) or youtube_video_id(url)
    if direct_id:
        return f"youtube:{direct_id}"
    title_key = compact_text(title)
    if title_has_practice_date(title_key, 5, 1):
        return FIVE_ONE_KEY
    if title_has_practice_date(title_key, 5, 2):
        return FIVE_TWO_KEY
    if title_has_practice_date(title_key, 5, 3):
        return FIVE_THREE_KEY
    direct_id = youtube_video_id(sample_id)
    if direct_id:
        return f"youtube:{direct_id}"
    return f"title:{title_key}" if title_key else ""


def source_key_from_item(item: dict[str, Any] | None) -> str:
    item = item or {}
    return source_key(
        url=item.get("sourceUrl") or item.get("url"),
        title=item.get("sourceTitle") or item.get("sampleTitle") or item.get("title"),
        sample_id=item.get("sampleId") or item.get("id") or item.get("sectionId"),
    )


def wieniawski_reference_target() -> dict[str, Any]:
    target = {
        "status": "reference_target_ready",
        "composer": "Henryk Wieniawski",
        "work": "Scherzo-Tarantelle, Op. 16",
        "movement": "",
        "part": "Solo violin",
        "keySignature": {
            "tonic": "G",
            "mode": "minor",
            "accidentalType": "flat",
            "accidentals": ["Bb", "Eb"],
            "label": "G minor / 2 flats",
        },
        "scoreSource": "IMSLP public-domain solo part",
        "scoreUrl": "https://imslp.org/wiki/Scherzo_tarantelle%2C_Op.16_%28Wieniawski%2C_Henri%29",
        "scorePdfUrl": "https://s9.imslp.org/files/imglnks/usimg/b/b0/IMSLP724668-PMLP17451-01._WIENIAWSKI_-_SCHERZO_TARANTELLE%2C_OP._16_%28GILSON%29_-_Solo_Part.pdf",
        "scorePdfLocalPath": "assets/score/wieniawski-scherzo-tarantelle-solo-imslp.pdf",
        "scoreAssetId": "wieniawski-scherzo-tarantelle-vln",
        "scorePage": 2,
        "scoreBoxes": [
            {"x": 14, "y": 14, "width": 74, "height": 12, "label": "Presto opening"},
            {"x": 13, "y": 26, "width": 75, "height": 20, "label": "early repetition pattern"},
        ],
        "referenceAudio": "needed",
        "symbolicScore": {
            "sourceId": "wieniawski-scherzo-tarantelle-opening-symbolic-v7",
            "title": "Wieniawski Scherzo-Tarantelle, Op. 16",
            "partId": "P1",
            "musicXmlPath": "assets/score/wieniawski-scherzo-tarantelle-symbolic-opening.musicxml",
            "candidateMapPath": "assets/score/wieniawski-scherzo-tarantelle-page2-score-map-candidates.json",
            "source": "Manually reviewed symbolic excerpts from the local IMSLP solo-violin PDF, page 2. The visible opening phrase begins A5-G5-F5-A5-G5-F5-A5-G#5-F5. The 2026-05-18 Staff 4 source-crop reverification accepted only the full-context actual-PDF crop for Eb5-Eb5-C5-Eb5-Eb5 after boxed source-note centers, rendered transcription, and paired audio all agreed by exact MIDI. The old tight crop, dependent six-, seven-, and eight-note extensions, previous D6-C6-Bb5 source sequence, lower-octave D5-C5-Bb4 map, D-Bb-G-D source sequence, stale Staff 4 D5 mismatch run, stitched A4 continuation, and user-rejected Bb-D-C-Bb-D lane remain rejected.",
            "sourcePdfLocalPath": "assets/score/wieniawski-scherzo-tarantelle-solo-imslp.pdf",
            "candidateMapStatus": "unaccepted_score_glyph_verification_queue",
            "verification": "source_score_note_sequence_verified_before_matching",
            "sourceSnippets": [
                {
                    "referenceStart": 9,
                    "referenceEnd": 14,
                    "label": "Staff 4 verified source window Eb-Eb-C-Eb-Eb",
                    "pitchClassSequence": ["D#", "D#", "C", "D#", "D#"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-context-review.png",
                    "sourceReviewImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-context-review.png",
                    "sourceCropDisplayAllowed": True,
                    "sourceCropReady": True,
                    "sourceCropRejected": False,
                    "sourceCropContextReady": True,
                    "sourcePdfPage": 2,
                    "status": "source_score_exact_midi_sequence_verified",
                    "verification": "verified_from_staff4_source_crop_reverification_exact_source_audio_2026_05_18",
                    "visualRangeAgreement": True,
                    "visibleScoreNoteSequenceVerified": True,
                    "visibleScoreExactNoteSequenceVerified": True,
                    "scoreBoxCenterAgreement": True,
                    "audioTranscriptionAgreement": True,
                    "transcriptionScoreAgreement": True,
                    "truthEvidenceAccepted": True,
                    "sourceCropKind": "actual_source_score_full_context_exact_note_range",
                    "minimumDistinctPitchClasses": 2,
                    "scoreSpellingSequence": ["Eb", "Eb", "C", "Eb", "Eb"],
                    "visibleScoreNoteSequence": ["Eb", "Eb", "C", "Eb", "Eb"],
                    "visibleScoreExactNoteSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5"],
                    "acceptedAudioPhrase": {
                        "practiceDay": "2026-05-03",
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "detectedExactNoteSequence": ["D#5", "D#5", "C5", "D#5", "D#5"],
                        "acceptedScoreSpellingSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5"],
                        "midiSequence": [75, 75, 72, 75, 75],
                        "audioAgreement": True
                    },
                    "sourceCropCoordinates": {
                        "sourceImage": "verification/wieniawski-page2-300.png",
                        "pagePixels": {"x": 2045, "y": 1378, "width": 235, "height": 140},
                        "matchedNoteheadCenters": [
                            {"note": "Eb5", "x": 2061.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2108.5, "y": 1435.0},
                            {"note": "C5", "x": 2153.0, "y": 1455.5},
                            {"note": "Eb5", "x": 2204.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2250.5, "y": 1435.0}
                        ]
                    }
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 15,
                    "label": "Staff 4 verified source window Eb-Eb-C-Eb-Eb-Eb",
                    "pitchClassSequence": ["D#", "D#", "C", "D#", "D#", "D#"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-context-review.png",
                    "sourceReviewImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-context-review.png",
                    "sourceCropDisplayAllowed": False,
                    "sourceCropReady": False,
                    "sourceCropRejected": True,
                    "sourceCropContextReady": True,
                    "sourcePdfPage": 2,
                    "status": "source_score_visual_reverified_audio_blocked",
                    "verification": "source_crop_visual_reverified_audio_blocked_sixth_note",
                    "visualRangeAgreement": True,
                    "visibleScoreNoteSequenceVerified": True,
                    "visibleScoreExactNoteSequenceVerified": True,
                    "scoreBoxCenterAgreement": True,
                    "audioTranscriptionAgreement": False,
                    "transcriptionScoreAgreement": False,
                    "truthEvidenceAccepted": False,
                    "sourceCropKind": "actual_source_score_full_context_exact_note_range",
                    "minimumDistinctPitchClasses": 2,
                    "scoreSpellingSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb"],
                    "visibleScoreNoteSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb"],
                    "visibleScoreExactNoteSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5"],
                    "acceptedAudioPhrase": {
                        "practiceDay": "2026-05-03",
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "detectedExactNoteSequence": ["D#5", "D#5", "C5", "D#5", "D#5", "D#5"],
                        "acceptedScoreSpellingSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5"],
                        "midiSequence": [75, 75, 72, 75, 75, 75],
                        "localStartSeconds": 20.225,
                        "localEndSeconds": 22.992,
                        "audioAgreement": True
                    },
                    "sourceCropCoordinates": {
                        "sourceImage": "verification/wieniawski-page2-300.png",
                        "pagePixels": {"x": 1995, "y": 1275, "width": 360, "height": 270},
                        "matchedNoteheadCenters": [
                            {"note": "Eb5", "x": 2061.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2108.5, "y": 1435.0},
                            {"note": "C5", "x": 2153.0, "y": 1455.5},
                            {"note": "Eb5", "x": 2204.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2250.5, "y": 1435.0},
                            {"note": "Eb5", "x": 2322.5, "y": 1435.0}
                        ]
                    },
                    "rejectionReason": "The source crop has a full-context actual-PDF six-note visual review image, but the sixth stored audio note is not accepted by the current pYIN/YIN/spectral agreement gate.",
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 16,
                    "label": "Staff 4 verified source extension Eb-Eb-C-Eb-Eb-Eb-C",
                    "pitchClassSequence": ["D#", "D#", "C", "D#", "D#", "D#", "C"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-source.png",
                    "sourcePdfPage": 2,
                    "status": "source_score_exact_midi_sequence_verified",
                    "verification": "verified_from_staff4_full_phrase_audit_v3_audio_agreed_2026_05_18",
                    "visualRangeAgreement": True,
                    "visibleScoreNoteSequenceVerified": True,
                    "visibleScoreExactNoteSequenceVerified": True,
                    "scoreBoxCenterAgreement": True,
                    "audioTranscriptionAgreement": True,
                    "transcriptionScoreAgreement": True,
                    "truthEvidenceAccepted": True,
                    "sourceCropKind": "actual_source_score_exact_note_range",
                    "minimumDistinctPitchClasses": 2,
                    "scoreSpellingSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb", "C"],
                    "visibleScoreNoteSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb", "C"],
                    "visibleScoreExactNoteSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5", "C5"],
                    "acceptedAudioPhrase": {
                        "practiceDay": "2026-05-03",
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "detectedExactNoteSequence": ["D#5", "D#5", "C5", "D#5", "D#5", "D#5", "C5"],
                        "acceptedScoreSpellingSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5", "C5"],
                        "midiSequence": [75, 75, 72, 75, 75, 75, 72],
                        "localStartSeconds": 20.225,
                        "localEndSeconds": 23.28,
                        "auditPacketId": "staff4-2026-05-03-Njh8_zq9_DM-8835-9-16",
                        "audioAgreement": True
                    },
                    "extensionCheck": {
                        "practiceDay": "2026-05-03",
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "acceptedPrefixMidiSequence": [75, 75, 72, 75, 75, 75],
                        "expectedNextScoreNote": "C5",
                        "expectedNextScoreMidi": 72,
                        "observedNextAudioNote": "C5",
                        "observedNextAudioMidi": 72,
                        "audioAgreement": True,
                        "resolution": "accepted_full_phrase_audit_v3",
                    },
                    "sourceCropCoordinates": {
                        "sourceImage": "verification/wieniawski-page2-300.png",
                        "pagePixels": {"x": 1995, "y": 1275, "width": 455, "height": 270},
                        "matchedNoteheadCenters": [
                            {"note": "Eb5", "x": 2061.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2108.5, "y": 1435.0},
                            {"note": "C5", "x": 2153.0, "y": 1455.5},
                            {"note": "Eb5", "x": 2204.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2250.5, "y": 1435.0},
                            {"note": "Eb5", "x": 2322.5, "y": 1435.0},
                            {"note": "C5", "x": 2369.5, "y": 1455.5}
                        ]
                    }
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 17,
                    "label": "Staff 4 verified source-only extension Eb-Eb-C-Eb-Eb-Eb-C-A",
                    "pitchClassSequence": ["D#", "D#", "C", "D#", "D#", "D#", "C", "A"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-a-source.png",
                    "sourcePdfPage": 2,
                    "status": "source_score_exact_midi_sequence_verified_source_only",
                    "verification": "verified_from_actual_staff4_source_crop_not_audio_accepted_2026_05_18",
                    "visualRangeAgreement": True,
                    "visibleScoreNoteSequenceVerified": True,
                    "visibleScoreExactNoteSequenceVerified": True,
                    "scoreBoxCenterAgreement": True,
                    "audioTranscriptionAgreement": False,
                    "transcriptionScoreAgreement": False,
                    "truthEvidenceAccepted": False,
                    "sourceCropKind": "actual_source_score_exact_note_range",
                    "minimumDistinctPitchClasses": 3,
                    "scoreSpellingSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb", "C", "A"],
                    "visibleScoreNoteSequence": ["Eb", "Eb", "C", "Eb", "Eb", "Eb", "C", "A"],
                    "visibleScoreExactNoteSequence": ["Eb5", "Eb5", "C5", "Eb5", "Eb5", "Eb5", "C5", "A4"],
                    "extensionCheck": {
                        "practiceDay": "2026-05-03",
                        "sampleId": "Njh8_zq9_DM-8835",
                        "sourceWindow": "*8835-8925",
                        "acceptedPrefixMidiSequence": [75, 75, 72, 75, 75, 75, 72],
                        "expectedNextScoreNote": "A4",
                        "expectedNextScoreMidi": 69,
                        "observedNextAudioNote": "A4",
                        "observedNextAudioMidi": 69,
                        "audioAgreement": True,
                        "phraseContinuous": False,
                        "maxInterNoteGapSeconds": 8.985,
                        "maxAllowedInterNoteGapSeconds": 3.0,
                        "resolution": "exact_midi_candidate_rejected_discontinuous_phrase"
                    },
                    "sourceCropCoordinates": {
                        "sourceImage": "verification/wieniawski-page2-300.png",
                        "pagePixels": {"x": 1995, "y": 1275, "width": 540, "height": 270},
                        "matchedNoteheadCenters": [
                            {"note": "Eb5", "x": 2061.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2108.5, "y": 1435.0},
                            {"note": "C5", "x": 2153.0, "y": 1455.5},
                            {"note": "Eb5", "x": 2204.0, "y": 1435.0},
                            {"note": "Eb5", "x": 2250.5, "y": 1435.0},
                            {"note": "Eb5", "x": 2322.5, "y": 1435.0},
                            {"note": "C5", "x": 2369.5, "y": 1455.5},
                            {"note": "A4", "x": 2410.0, "y": 1477.5}
                        ]
                    }
                },
                {
                    "referenceStart": 0,
                    "referenceEnd": 7,
                    "label": "opening D-C-Bb-D-C-Bb-D",
                    "pitchClassSequence": ["D", "C", "A#", "D", "C", "A#", "D"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-opening-d-c-bb-d-c-bb-d-source.png",
                    "sourcePdfPage": 2,
                    "status": "source_score_phrase_review_rejected",
                    "verification": "visual_range_mismatch_review_required",
                    "visualRangeAgreement": False,
                    "visibleScoreNoteSequenceVerified": False,
                    "sourceCropKind": "actual_source_score_review_crop",
                    "scoreSpellingSequence": ["D", "C", "Bb", "D", "C", "Bb", "D"],
                    "rejectionReason": "This source crop remains review material only; it is not accepted as score evidence until visible noteheads and register are verified against the transcription.",
                },
                {
                    "referenceStart": 2,
                    "referenceEnd": 7,
                    "label": "opening Bb-D-C-Bb-D",
                    "pitchClassSequence": ["A#", "D", "C", "A#", "D"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-opening-bb-d-c-bb-d-exact-source.png",
                    "sourcePdfPage": 2,
                    "status": "source_score_phrase_review_rejected",
                    "verification": "visible_noteheads_and_box_centers_failed_review",
                    "visualRangeAgreement": False,
                    "visibleScoreNoteSequenceVerified": False,
                    "visibleScoreExactNoteSequenceVerified": False,
                    "scoreBoxCenterAgreement": False,
                    "audioTranscriptionAgreement": False,
                    "transcriptionScoreAgreement": False,
                    "truthEvidenceAccepted": False,
                    "sourceCropKind": "actual_source_score_exact_note_range",
                    "scoreSpellingSequence": ["Bb", "D", "C", "Bb", "D"],
                    "visibleScoreNoteSequence": ["Bb", "D", "C", "Bb", "D"],
                    "visibleScoreExactNoteSequence": ["Bb4", "D5", "C5", "Bb4", "D5"],
                    "sourceCropCoordinates": {
                        "sourceImage": "verification/wieniawski-page2-300.png",
                        "pagePixels": {"x": 1050, "y": 468, "width": 262, "height": 157},
                        "matchedNoteheadCenters": [
                            {"note": "Bb4", "x": 1083, "y": 574},
                            {"note": "D5", "x": 1134, "y": 509},
                            {"note": "C5", "x": 1190, "y": 529},
                            {"note": "Bb4", "x": 1235, "y": 573},
                            {"note": "D5", "x": 1289, "y": 493},
                        ],
                    },
                    "rejectionReason": "Alan's review showed the displayed source-score crop and boxes did not match the transcription closely enough to count as accepted evidence.",
                    "verificationLimit": "This remains a rejected review fixture until notehead centers, score notes, transcription notes, and paired audio all agree.",
                },
                {
                    "referenceStart": 2,
                    "referenceEnd": 7,
                    "label": "opening Bb-D-C-Bb-D exact source crop",
                    "pitchClassSequence": ["A#", "D", "C", "A#", "D"],
                    "imageUrl": "/assets/score/wieniawski-scherzo-tarantelle-opening-bb-d-c-bb-d-exact-source-clean.png",
                    "sourcePdfPage": 2,
                    "status": "source_score_phrase_review_rejected",
                    "verification": "alan_rejected_five_note_phrase_2026_05_15",
                    "visualRangeAgreement": False,
                    "visibleScoreNoteSequenceVerified": False,
                    "visibleScoreExactNoteSequenceVerified": False,
                    "scoreBoxCenterAgreement": False,
                    "audioTranscriptionAgreement": False,
                    "transcriptionScoreAgreement": False,
                    "truthEvidenceAccepted": False,
                    "sourceCropKind": "actual_source_score_exact_note_range",
                    "scoreSpellingSequence": ["Bb", "D", "C", "Bb", "D"],
                    "visibleScoreNoteSequence": ["Bb", "D", "C", "Bb", "D"],
                    "visibleScoreExactNoteSequence": ["Bb4", "D5", "C5", "Bb4", "D5"],
                    "sourceCropCoordinates": {
                        "sourceImage": "assets/score/wieniawski-scherzo-tarantelle-solo-imslp.pdf page 2",
                        "pagePixels": {"x": 625, "y": 292, "width": 270, "height": 146},
                        "matchedNoteheadCenters": [
                            {"note": "Bb4", "x": 642, "y": 373},
                            {"note": "D5", "x": 706, "y": 314},
                            {"note": "C5", "x": 744, "y": 337},
                            {"note": "Bb4", "x": 796, "y": 373},
                            {"note": "D5", "x": 845, "y": 304}
                        ],
                    },
                    "rejectionReason": "Alan reviewed the displayed five-note phrase and said it is not correct; this exact lane must not display as accepted score evidence.",
                    "verificationLimit": "Do not re-promote this five-note lane without new independent audio, transcription, source-score, and musician review.",
                }
            ],
            "rejectedSourceSnippetRanges": [
                {
                    "referenceStart": 9,
                    "referenceEnd": 14,
                    "status": "superseded_by_staff4_context_crop_reverified_2026_05_18",
                    "reason": "The old tight crop remains blocked, but the exact 9-14 source range can now display only through the full-context actual-PDF reverification crop.",
                    "blockedImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-verified.png",
                    "sourceReviewImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-context-review.png",
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 15,
                    "status": "blocked_visual_source_reverified_audio_review_required_2026_05_18",
                    "reason": "This six-note Staff 4 range has a full-context actual-PDF source crop for review, but it cannot display as accepted evidence until the sixth stored audio note passes exact per-note detector agreement.",
                    "blockedImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-verified.png",
                    "sourceReviewImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-context-review.png",
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 16,
                    "status": "blocked_dependent_on_rejected_staff4_visible_anchor_2026_05_18",
                    "reason": "This seven-note Staff 4 range extends the rejected five-note visible anchor and cannot be accepted until the source crop and transcription are reverified.",
                    "blockedImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-source.png",
                },
                {
                    "referenceStart": 9,
                    "referenceEnd": 17,
                    "status": "blocked_dependent_on_rejected_staff4_visible_anchor_2026_05_18",
                    "reason": "This eight-note Staff 4 source-only range extends the rejected visible anchor and the current audio search is discontinuous.",
                    "blockedImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-staff4-eb-eb-c-eb-eb-eb-c-a-source.png",
                },
            ],
        },
        "rejectedScorePhraseSequences": [
            {
                "pitchClassSequence": ["A#", "D", "C", "A#", "D"],
                "visibleScoreExactNoteSequence": ["Bb4", "D5", "C5", "Bb4", "D5"],
                "status": "alan_rejected_2026_05_15",
                "reason": "The displayed five-note Scherzo phrase was rejected after review and must stay candidate-only.",
            },
            {
                "pitchClassSequence": ["D", "A#", "G", "D"],
                "status": "alan_rejected_prior_score_sequence",
                "reason": "Earlier D-Bb-G-D score extraction was wrong for the actual source-score location.",
            },
        ],
        "symbolicScoreStatus": "symbolic_score_ready",
        "symbolicScoreRequirement": "Accepted score matches require parsed symbolic notes from the source score, not scanned-image note guesses.",
        "symbolicScoreMinimumMatchedNoteRun": 4,
        "symbolicScoreMinimumDistinctPitchClasses": 2,
        "scoreNoteDetectionStatus": "source_symbolic_excerpt_ready",
        "scoreLocationStatus": "actual_source_phrase_review_pending",
        "scorePitchClassAnchors": [],
        "rejectedScorePitchClassAnchors": [
            {
                "pitchClass": "A",
                "displayNote": "A4",
                "status": "rejected_visual_note_review",
                "reason": "The boxed source-score crop was reported as B-position notation while the audio transcription was A4; it is not accepted evidence.",
                "snippetImageUrl": "/assets/score/wieniawski-scherzo-tarantelle-a4-source-verified.png",
            },
            {
                "pitchClass": "A",
                "displayNote": "A4",
                "status": "rejected_visual_note_review",
                "reason": "The previous A4 crop was reported as G4, not A4, and remains rejected.",
            },
            {
                "pitchClass": "A",
                "displayNote": "A5",
                "status": "rejected_visual_note_review",
                "reason": "The previous A5 crop was reported as G5, not A5, and remains rejected.",
            },
        ],
        "scoreNoteCropStatus": "actual_source_phrase_review_pending",
        "referencePitchClassSequences": [
            {
                "label": "Scherzo-Tarantelle reference audio pitch trace, first 180 seconds",
                "source": "local reference audio transcription",
                "sequenceKind": "reference_audio_pitch_trace",
                "scoreLocationStatus": "exact_score_location_pending",
                "values": WIENIAWSKI_REFERENCE_AUDIO_PITCH_CLASSES,
            }
        ],
        "alignmentGoal": "Match extracted solo-violin pitch/rhythm to Scherzo-Tarantelle sections, then report phrase, section, or measure range.",
        "passageVocabulary": [
            "Presto opening",
            "introduction bars 1-4",
            "main theme bars 5-9",
            "Maggiore / Tranquillo cantilena",
            "solo cadenza",
            "returning refrain and coda",
        ],
    }
    rejected_range_items = {
        (
            int(item.get("referenceStart") or -1),
            int(item.get("referenceEnd") or -1),
        ): item
        for item in target["symbolicScore"].get("rejectedSourceSnippetRanges", [])
        if isinstance(item, dict)
        and any(token in str(item.get("status") or "").lower() for token in ("rejected", "mismatch", "blocked"))
    }
    for snippet in target["symbolicScore"].get("sourceSnippets", []):
        if not isinstance(snippet, dict):
            continue
        identity = (int(snippet.get("referenceStart") or -1), int(snippet.get("referenceEnd") or -1))
        if identity not in rejected_range_items:
            continue
        rejected_item = rejected_range_items.get(identity) or {}
        status = str(rejected_item.get("status") or "").lower()
        if "visual_source_reverified_audio_review_required" in status:
            snippet["status"] = "source_score_visual_reverified_audio_blocked"
            snippet["verification"] = "visual_source_reverified_audio_review_required"
            snippet["audioTranscriptionAgreement"] = False
            snippet["transcriptionScoreAgreement"] = False
            snippet["truthEvidenceAccepted"] = False
            snippet["sourceCropDisplayAllowed"] = False
            snippet["sourceCropReady"] = False
            snippet["sourceCropRejected"] = True
            snippet["sourceCropContextReady"] = True
            snippet["rejectionReason"] = (
                "The source crop is visually reverified, but the paired audio is not accepted for the full range."
            )
            continue
        snippet["status"] = "source_score_phrase_review_rejected"
        snippet["verification"] = "alan_rejected_visible_score_transcription_mismatch_2026_05_18"
        snippet["visualRangeAgreement"] = False
        snippet["visibleScoreNoteSequenceVerified"] = False
        snippet["visibleScoreExactNoteSequenceVerified"] = False
        snippet["scoreBoxCenterAgreement"] = False
        snippet["audioTranscriptionAgreement"] = False
        snippet["transcriptionScoreAgreement"] = False
        snippet["truthEvidenceAccepted"] = False
        snippet["rejectionReason"] = (
            "Alan reviewed the live displayed Staff 4 score/transcription pair and reported that the notes do not match."
        )
    return target


def builtin_correction(key: str) -> dict[str, Any] | None:
    if key == FIVE_ONE_KEY:
        return {
            "sourceKey": FIVE_ONE_KEY,
            "sourceTitle": "5-1-26",
            "sourceUrl": "https://www.youtube.com/watch?v=wDfVpTU4I_I",
            "rejectedTitles": FIVE_ONE_REJECTED_TITLES,
            "acceptedTitle": FIVE_ONE_ACCEPTED_TITLE,
            "sourceTip": "Haydn finale: light bow, even rhythm.",
            "updatedAt": "2026-05-08T00:00:00+00:00",
            "sourceHint": "Alan-confirmed source label: Haydn Symphony No. 94, last movement, Violin I part.",
            "referenceTarget": {
                "status": "reference_target_ready",
                "composer": "Joseph Haydn",
                "work": "Symphony No. 94 in G major, Hob.I:94",
                "movement": "IV. Finale",
                "part": "Violin I",
                "keySignature": {
                    "tonic": "G",
                    "mode": "major",
                    "accidentalType": "sharp",
                    "accidentals": ["F#"],
                    "label": "G major / 1 sharp",
                },
                "scoreSource": "IMSLP",
                "scoreUrl": "https://imslp.org/wiki/Symphony_No.94_%28Haydn%2C_Joseph%29",
                "scorePdfUrl": "https://vmirror.imslp.org/files/imglnks/usimg/8/87/IMSLP360278-PMLP34746-Haydn%3B_Symphony_94_Corrected.pdf",
                "scoreAssetId": "haydn-94-finale-score",
                "scorePage": 45,
                "scoreBoxes": [
                    {"x": 17, "y": 35, "width": 72, "height": 8, "label": "Violin I opening figure"},
                    {"x": 17, "y": 75, "width": 72, "height": 7, "label": "Violin I continuation"},
                ],
                "referenceAudio": "needed",
                "alignmentGoal": "Match extracted violin pitch/rhythm to the Finale violin I part, then report section or measure range.",
                "passageVocabulary": [
                    "Finale / Allegro molto",
                    "orchestral Violin I part",
                    "light repeated-note and running-note Haydn finale figures",
                    "not a solo concerto, caprice, sonata, partita, or showpiece",
                ],
            },
            "reason": "Alan-corrected false labels and supplied the accepted 5/1 source label.",
        }
    if key == FIVE_TWO_KEY:
        return {
            "sourceKey": FIVE_TWO_KEY,
            "sourceTitle": "5-2-26",
            "sourceUrl": "https://www.youtube.com/watch?v=K38CgZhvF3Q",
            "rejectedTitles": [],
            "acceptedTitle": FIVE_TWO_ACCEPTED_TITLE,
            "sourceTip": "Scherzo-Tarantelle: keep the bow stroke small, even, and rhythm-first before tempo.",
            "updatedAt": "2026-05-08T00:00:00+00:00",
            "sourceHint": "Alan-confirmed source label: Wieniawski Scherzo-Tarantelle, Op. 16.",
            "referenceTarget": wieniawski_reference_target(),
            "reason": "Alan supplied the accepted 5/2 source label.",
        }
    if key == FIVE_THREE_KEY:
        return {
            "sourceKey": FIVE_THREE_KEY,
            "sourceTitle": "5-3-26",
            "sourceUrl": "https://www.youtube.com/watch?v=Njh8_zq9_DM",
            "rejectedTitles": [],
            "acceptedTitle": FIVE_TWO_ACCEPTED_TITLE,
            "sourceTip": "Scherzo-Tarantelle: preserve the bounce without letting repetitions grow large.",
            "updatedAt": "2026-05-08T00:00:00+00:00",
            "sourceHint": "Alan-confirmed source label: 5/3 violin footage is Wieniawski Scherzo-Tarantelle, Op. 16. Treat same-day violin footage as this piece unless score/audio strongly contradicts it.",
            "referenceTarget": wieniawski_reference_target(),
            "reason": "Alan supplied the accepted 5/3 source label and confirmed all violin footage that day was Scherzo-Tarantelle.",
        }
    return None


def correction_for_key(state: dict[str, Any], key: str) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "sourceKey": key,
        "rejectedTitles": [],
        "acceptedTitle": "",
        "updatedAt": "",
        "reason": "",
    }
    built_in = builtin_correction(key)
    if built_in:
        merged.update(built_in)
    stored = state.get("sourceCorrections", {}).get(key)
    if isinstance(stored, dict):
        rejected = [
            *merged.get("rejectedTitles", []),
            *[str(item).strip() for item in stored.get("rejectedTitles", []) if str(item).strip()],
        ]
        merged.update(stored)
        merged["rejectedTitles"] = list(dict.fromkeys(rejected))
    return merged


def correction_for_item(state: dict[str, Any], item: dict[str, Any] | None) -> dict[str, Any]:
    key = source_key_from_item(item)
    return correction_for_key(state, key) if key else {"rejectedTitles": [], "acceptedTitle": ""}


def accepted_source_corrections(state: dict[str, Any]) -> list[dict[str, Any]]:
    keys = list(BUILTIN_CORRECTION_KEYS)
    stored = state.get("sourceCorrections")
    if isinstance(stored, dict):
        keys.extend(str(key) for key in stored if str(key).strip())
    accepted: list[dict[str, Any]] = []
    for key in dict.fromkeys(keys):
        correction = correction_for_key(state, key)
        if compact_text(correction.get("acceptedTitle")):
            accepted.append(correction)
    return accepted


def title_rejected_for_item(title: Any, state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    compact = compact_text(title)
    if not compact:
        return False
    correction = correction_for_item(state, item)
    for rejected in correction.get("rejectedTitles", []):
        rejected_compact = compact_text(rejected)
        if rejected_compact and (
            compact == rejected_compact or compact in rejected_compact or rejected_compact in compact
        ):
            return True
    return False


def source_requires_confirmed_acceptance(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    key = source_key_from_item(item)
    if not key:
        return False
    correction = correction_for_key(state, key)
    if compact_text(correction.get("acceptedTitle")):
        return False
    rejected_titles = {
        compact_text(title)
        for title in correction.get("rejectedTitles", [])
        if compact_text(title)
    }
    return len(rejected_titles) >= SOURCE_ACCEPTANCE_REJECT_COUNT


def parsed_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def item_stale_after_source_correction(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    item = item or {}
    key = source_key_from_item(item)
    if not key:
        return False
    correction = correction_for_key(state, key)
    if not correction.get("rejectedTitles"):
        return False
    accepted = compact_text(correction.get("acceptedTitle"))
    if accepted:
        title_candidates = [
            item.get("title"),
            item.get("proposedTitle"),
            item.get("candidateTitle"),
            item.get("verificationTitle"),
        ]
        if any(
            (candidate := compact_text(title))
            and (candidate == accepted or candidate in accepted or accepted in candidate)
            for title in title_candidates
        ):
            return False
    corrected_at = parsed_at(correction.get("updatedAt"))
    if corrected_at is None:
        return False
    item_times = [
        parsed_at(item.get("createdAt")),
        parsed_at(item.get("latestAt")),
        parsed_at(item.get("updatedAt")),
    ]
    item_times = [value for value in item_times if value is not None]
    return not item_times or max(item_times) <= corrected_at


def rejected_title_on_item(state: dict[str, Any], item: dict[str, Any] | None) -> bool:
    item = item or {}
    titles: list[Any] = [
        item.get("title"),
        item.get("proposedTitle"),
        item.get("candidateTitle"),
        item.get("verificationTitle"),
    ]
    verification = item.get("verification")
    if isinstance(verification, dict):
        titles.append(verification.get("title"))
    for candidate in item.get("topCandidates", []):
        if isinstance(candidate, dict):
            titles.append(candidate.get("title"))
    return any(title_rejected_for_item(title, state, item) for title in titles)


def scrubbed_piece_item(item: dict[str, Any]) -> dict[str, Any]:
    current = dict(item)
    rejected_title = str(
        current.get("title")
        or current.get("proposedTitle")
        or current.get("candidateTitle")
        or current.get("verificationTitle")
        or ""
    ).strip()
    if rejected_title and rejected_title != "Piece being identified":
        current["rejectedTitle"] = rejected_title
    current["status"] = "piece_rejected_guess"
    current["title"] = "Piece being identified"
    current["confidence"] = "unknown"
    current["confidenceScore"] = 0
    current["completionPercent"] = 0
    current["todayCompletionPercent"] = 0
    current["readinessStatus"] = "piece_identification_pending"
    current["evidenceQuality"] = "weak"
    current["proposedTitle"] = ""
    current["candidateTitle"] = ""
    current["verificationTitle"] = ""
    current["candidateEvidence"] = "Rejected source-specific false label. Exact piece pending."
    current["evidence"] = "Rejected source-specific false label. Exact piece pending."
    current["rejectedByCorrection"] = True
    current["topCandidates"] = []
    current["verification"] = {}
    current["musicalClues"] = []
    current["notes"] = "Rejected source-specific false label. Exact piece pending."
    daily = current.get("daily")
    if isinstance(daily, dict):
        current["daily"] = {
            str(day): {
                **entry,
                "completionPercent": 0,
                "tip": "Piece identification pending verified source evidence.",
            }
            for day, entry in daily.items()
            if isinstance(entry, dict)
        }
    return current


def scrub_rejected_source(state: dict[str, Any], key: str) -> int:
    changed = 0
    review = state.setdefault("review", {})

    for collection_name in ("pieceIdentifications", "pieces"):
        collection = review.get(collection_name)
        if not isinstance(collection, list):
            continue
        scrubbed: list[Any] = []
        for item in collection:
            if (
                isinstance(item, dict)
                and item_matches_source_key(item, key)
                and (
                    rejected_title_on_item(state, item)
                    or item_stale_after_source_correction(state, item)
                    or source_requires_confirmed_acceptance(state, item)
                )
            ):
                scrubbed.append(scrubbed_piece_item(item))
                changed += 1
            else:
                scrubbed.append(item)
        review[collection_name] = scrubbed

    last_piece_id = state.get("lastPieceIdRun")
    if isinstance(last_piece_id, dict) and isinstance(last_piece_id.get("results"), list):
        scrubbed_results: list[Any] = []
        for item in last_piece_id["results"]:
            if (
                isinstance(item, dict)
                and item_matches_source_key(item, key)
                and (
                    rejected_title_on_item(state, item)
                    or item_stale_after_source_correction(state, item)
                    or source_requires_confirmed_acceptance(state, item)
                )
            ):
                scrubbed_results.append(scrubbed_piece_item(item))
                changed += 1
            else:
                scrubbed_results.append(item)
        last_piece_id["results"] = scrubbed_results
        identified = [
            item
            for item in scrubbed_results
            if isinstance(item, dict) and item.get("status") == "piece_identified"
        ]
        last_piece_id["identifiedCount"] = len(identified)
        if not identified and last_piece_id.get("status") == "piece_identified":
            last_piece_id["status"] = "piece_unidentified"

    current_work = str(review.get("currentWork") or "")
    key_item = {
        "url": key.split(":", 1)[1] if key.startswith("youtube:") else "",
        "sourceTitle": key.split(":", 1)[1] if key.startswith("title:") else "",
    }
    if current_work and (
        title_rejected_for_item(current_work, state, key_item)
        or source_requires_confirmed_acceptance(state, key_item)
    ):
        review["currentWork"] = "Piece identification pending verified source evidence."
        changed += 1

    return changed


def learn_rejection(
    state: dict[str, Any],
    *,
    source_url: str = "",
    source_title: str = "",
    video_id: str = "",
    rejected_title: str = "",
    note: str = "",
) -> dict[str, Any]:
    key = source_key(url=source_url, title=source_title, video_id=video_id)
    if not key:
        raise ValueError("source key required")
    corrections = state.setdefault("sourceCorrections", {})
    current = dict(corrections.get(key) or {})
    rejected = [
        *[str(item).strip() for item in current.get("rejectedTitles", []) if str(item).strip()],
        rejected_title.strip(),
    ]
    current.update(
        {
            "sourceKey": key,
            "sourceUrl": source_url,
            "sourceTitle": source_title,
            "rejectedTitles": list(dict.fromkeys(item for item in rejected if item)),
            "updatedAt": utc_now(),
        }
    )
    if note.strip():
        notes = [str(item).strip() for item in current.get("notes", []) if str(item).strip()]
        current["notes"] = [note.strip(), *notes][:10]
    corrections[key] = current
    return current


def learn_acceptance(
    state: dict[str, Any],
    *,
    source_url: str = "",
    source_title: str = "",
    video_id: str = "",
    accepted_title: str = "",
    note: str = "",
) -> dict[str, Any]:
    key = source_key(url=source_url, title=source_title, video_id=video_id)
    accepted_title = accepted_title.strip()
    if not key:
        raise ValueError("source key required")
    if not accepted_title or accepted_title == "Piece being identified":
        raise ValueError("accepted title required")
    corrections = state.setdefault("sourceCorrections", {})
    current = dict(corrections.get(key) or {})
    current.update(
        {
            "sourceKey": key,
            "sourceUrl": source_url,
            "sourceTitle": source_title,
            "acceptedTitle": accepted_title,
            "acceptedAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    if note.strip():
        notes = [str(item).strip() for item in current.get("notes", []) if str(item).strip()]
        current["notes"] = [note.strip(), *notes][:10]
    corrections[key] = current
    return current


def item_matches_source_key(item: dict[str, Any], key: str) -> bool:
    return bool(key) and source_key_from_item(item) == key
