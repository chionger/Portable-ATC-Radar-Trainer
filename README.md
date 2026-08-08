# Portable ATC Radar Trainer

An experimental **portable, offline-capable Air Traffic Control radar training platform** exploring how real-time simulation, local AI and speech technologies can be combined to support human-centred ATC training.

> **Project Status:** Early development / Phase 1

## Project Vision

The long-term goal is to develop a low-cost ATC training architecture capable of running locally with minimal dependence on cloud services.

The system is intended to explore the use of AI-driven virtual pilots and controllers that can communicate naturally with a human trainee while interacting with a real-time air traffic simulation.

The radar trainer is the first step toward a broader portable ATC training platform.

## Phase 1 Goal

Phase 1 focuses on establishing the minimum end-to-end architecture needed for a working training loop.

```text id="jtr0x4"
Human Controller
       │
       │ Voice
       ▼
Whisper ASR
       │
       ▼
Command / Agent Layer
       │
       ▼
Local LLM
       │
       ▼
BlueSky Simulation
       │
       ▼
Unity Radar Display

Virtual Pilot Response
       │
       ▼
Piper / Kokoro TTS
       │
       ▼
Human Controller
```

System events and interactions are recorded in SQLite to support replay and later training analysis.

## Planned Technology Stack

| Layer                  | Technology      |
| ---------------------- | --------------- |
| Visualisation          | Unity           |
| Air traffic simulation | BlueSky         |
| Speech recognition     | Whisper         |
| AI / virtual pilot     | Local LLM       |
| Speech synthesis       | Piper or Kokoro |
| Replay / event storage | SQLite          |

The architecture is intentionally designed around technologies that can operate locally.

## Design Principles

### Local First

Core training functionality should be capable of operating without continuous cloud connectivity.

### Low Latency

Voice interaction and simulation responses should remain responsive enough for real-time training.

### Modular Architecture

Speech recognition, AI reasoning, simulation, visualisation and replay should remain separate components connected through well-defined interfaces.

### Deterministic Simulation

AI-generated dialogue should not directly manipulate simulation state.

Validated commands should be converted into deterministic simulation events before affecting aircraft or scenario state.

### Replayability

Important trainee, AI and simulation events should be recorded so a training session can later be reconstructed and analysed.

### Human-Centred Training

AI exists to support the training of human controllers rather than replacing the human trainee.

## Initial Architecture

```text id="s62hsa"
Human Trainee
     │
     ▼
Whisper ASR
     │
     ▼
Agent / Command Layer
     │
     ├──────────────► Local LLM
     │                    │
     │                    ▼
     │               Piper / Kokoro
     │                    │
     │                    ▼
     │               Voice Response
     │
     ▼
BlueSky Simulation
     │
     ▼
Unity Radar Display

All significant events
     │
     ▼
SQLite Replay Database
```

This architecture will evolve as the prototype develops.

## Repository Structure

```text id="o5d8x2"
Portable-ATC-Radar-Trainer/
├── README.md
├── LICENSE
├── .gitignore
│
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── phase-1/
│   └── diagrams/
│
├── unity/
│
├── services/
│   ├── asr/
│   ├── llm/
│   ├── tts/
│   └── bluesky/
│
├── replay/
├── tests/
└── scripts/
```

The structure may change as implementation experience reveals better boundaries between components.

## Development Approach

The project will be developed incrementally.

Each major capability should first work independently before being integrated into the complete training loop.

```text id="y4wmyi"
Simulation
    ↓
Radar Visualisation
    ↓
Speech Recognition
    ↓
Command Interpretation
    ↓
Virtual Pilot Response
    ↓
Speech Synthesis
    ↓
Replay
    ↓
Integrated Training Scenario
```

The emphasis is on getting a small end-to-end system working before increasing realism or complexity.

## Longer-Term Direction

Future phases may explore:

* Multiple virtual aircraft and pilots
* Multiple ATC sectors or controller positions
* Standard ATC phraseology
* Deliberately incorrect pilot readbacks
* Different speech characteristics and accents
* Cross-transmissions and frequency congestion
* Adaptive training scenarios
* Instructor controls
* Session rollback and continuation
* Competency assessment
* AI-assisted coaching and debrief
* Tower and aerodrome visual simulation
* Multi-user training
* Higher-fidelity visual environments

These capabilities are **future directions**, not current Phase 1 functionality.

## Project Status

This repository currently represents an **early-stage research and engineering prototype**.

Architecture, interfaces and technology choices may change as individual components are tested and integrated.

The immediate objective is to prove a reliable local end-to-end training loop before attempting higher fidelity or larger-scale deployment.

## License

Licensed under the **Apache License 2.0**.

---

**Current focus:** Phase 1 — establish the portable ATC radar trainer foundation.
