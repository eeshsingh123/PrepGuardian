# PrepGuardian 🛡️

PrepGuardian is a live AI companion designed to transform how users learn and prepare for high-stakes scenarios. Built entirely within the **Antigravity IDE** and powered by **Google’s fundamental AI stack**, it provides a seamless, multi-modal interaction experience that feels less like a tool and more like a dedicated mentor.

---

## 🚀 How it Works (The Flow)

PrepGuardian operates in a continuous, low-latency loop that bridges the gap between digital content and human interaction:

1.  **Context Injection**: The user triggers a session, and their specific background (experience, goals, and learning style) is dynamically injected into the agent's context.
2.  **Live Interaction**: Users engage with the agent via real-time voice and screen sharing. The agent "sees" what the user sees and hears what they say.
3.  **Intelligent Reasoning**: Powered by Gemini Live (ADK), the agent processes visual and auditory cues simultaneously to provide contextual feedback, solve problems, or conduct mock interviews.
4.  **Graceful Termination**: Sessions end with a clean wrap-up, where transcripts are automatically saved and processed for future review, ensuring no insight is lost.

## ✨ What PrepGuardian Does Well

*   **Human-First Interaction**: Uses real-time voice and interruption-aware audio to make conversations feel natural and fluid.
*   **Visual Awareness**: Through integrated screen sharing, the agent can guide users through complex software, codebases, or documents as if it were sitting right next to them.
*   **Contextual Memory**: Every session builds upon the last. By storing and retrieving conversation histories, the agent maintains a persistent understanding of the user's progress.
*   **Low Friction**: No complex setup. Start a session, share your goals, and get straight to work.

## 🛠️ Tech Stack

### AI & Core Engine
*   **Google ADK**: For robust, streaming-first agent architecture.
*   **Google GenAI (Gemini 2.0 Flash / Live)**: The brain behind the multi-modal reasoning.
*   **Antigravity IDE**: The primary development environment used to build this entire stack.

### Backend (The Backbone)
*   **FastAPI**: For high-performance, asynchronous API endpoints.
*   **Python 3.14**: Utilizing the latest language features for speed and reliability.
*   **UV**: Used for lightning-fast dependency management and builds.
*   **MongoDB (Motor)**: Async storage for user context and conversation transcripts.

### Frontend (The Interface)
*   **React & Vite**: A modern, snappy user interface.
*   **TanStack Query**: For efficient server-state management.
*   **Tailwind CSS 4**: For a lean, high-fidelity design system.

## 🌍 Impact on the User

PrepGuardian isn't just about answering questions; it's about **reducing the cognitive load** of learning. By providing a 24/7 "guardian" that understands both the verbal nuances and the visual context of a task, it enables:

*   **Faster Mastery**: Real-time correction and guidance during active work.
*   **Increased Confidence**: A safe, intelligent space to practice interviews or presentations.
*   **Personalization at Scale**: An AI that actually knows you, your history, and your specific hurdles.
