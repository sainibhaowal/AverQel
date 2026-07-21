import logging
import math
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class QSATPredictor:
    """
    Quantum Semantic Action Terminal (QSAT) Predictor.
    Models workspace shell environments as physical systems in a Hamiltonian phase space.
    Calculates Shannon Entropy and transition vectors for command autocompletion.
    """

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.command_history = [
            "docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.localprod up -d --build --remove-orphans",
            "pnpm build",
            "pnpm dev",
            "git status",
            "git diff",
            "git add .",
            "python3 -m venv .venv",
            "source .venv/bin/activate",
            "pip install fastapi uvicorn"
        ]
        self._cached_state = None
        self._last_calc_time = 0.0

    def record_command(self, command: str):
        """Record command executions to update Markov transition chains."""
        cmd = command.strip()
        if cmd and cmd not in self.command_history:
            self.command_history.insert(0, cmd)
            if len(self.command_history) > 50:
                self.command_history.pop()
        # Invalidate cache so next request recalculates with fresh directory metrics
        self._cached_state = None

    def get_phase_state(self, cwd: str) -> dict:
        """
        Computes Hamiltonian coordinates:
        q (Potential Energy V(q) based on codebase size and complexity metrics)
        p (Kinetic Energy T(p) based on activity levels and rate of command runs)
        """
        import time
        now = time.time()
        if self._cached_state is not None and (now - self._last_calc_time < 20.0):
            return self._cached_state

        try:
            target_dir = Path(cwd)
            if not target_dir.exists():
                target_dir = self.workspace_path

            # Count files and estimate complexity (V(q))
            file_count = 0
            lines_of_code = 0
            for root, _, files in os.walk(target_dir):
                # Ignore node_modules and hidden folders
                if any(x in root for x in ["node_modules", ".git", ".next", "__pycache__", ".venv"]):
                    continue
                for f in files:
                    file_count += 1
                    fpath = os.path.join(root, f)
                    try:
                        if os.path.getsize(fpath) < 500000: # limit to small files
                            with open(fpath, errors="ignore") as file_obj:
                                lines_of_code += len(file_obj.readlines())
                    except Exception:
                        pass

            # Potential energy V(q) maps logarithmically to code structures
            potential_energy = float(round(1.5 * math.log(max(file_count, 1)) + 0.1 * math.log(max(lines_of_code, 1)), 2))
        except Exception:
            potential_energy = 1.0

        # Kinetic energy T(p) maps to frequency and density of active historical commands
        kinetic_energy = float(round(0.5 * len(self.command_history) + 0.25, 2))
        total_energy = float(round(potential_energy + kinetic_energy, 2))

        # Calculate workspace state Shannon Entropy H(X)
        entropy = float(round(self._calculate_entropy(cwd), 2))

        result = {
            "potential_energy": potential_energy,
            "kinetic_energy": kinetic_energy,
            "total_energy": total_energy,
            "entropy": entropy,
            "coordinate_q": float(round(math.sin(potential_energy) * 5, 2)),
            "coordinate_p": float(round(math.cos(kinetic_energy) * 5, 2))
        }
        self._cached_state = result
        self._last_calc_time = now
        return result

    def _calculate_entropy(self, cwd: str) -> float:
        """Calculate file extension distribution entropy to map directory diversity."""
        try:
            target_dir = Path(cwd)
            if not target_dir.exists():
                target_dir = self.workspace_path

            extensions = []
            for root, _, files in os.walk(target_dir):
                if any(x in root for x in ["node_modules", ".git", ".next", "__pycache__", ".venv"]):
                    continue
                for f in files:
                    ext = Path(f).suffix
                    if ext:
                        extensions.append(ext)

            if not extensions:
                return 0.0

            freqs = {}
            for ext in extensions:
                freqs[ext] = freqs.get(ext, 0) + 1

            total = len(extensions)
            entropy = 0.0
            for count in freqs.values():
                p = count / total
                entropy -= p * math.log2(p)
            return entropy
        except Exception:
            return 1.2

    def predict_next_command(self, current_input: str, cwd: str) -> dict:
        """
        Uses prefix matching and contextual heuristics to propose the command line completion
        that minimizes state uncertainty.
        """
        prefix = current_input.strip()
        if not prefix:
            return {"prediction": "", "probability": 0.0}

        # Filter command history that starts with current prefix (case-insensitive)
        candidates = [cmd for cmd in self.command_history if cmd.lower().startswith(prefix.lower())]

        if not candidates:
            # Contextual backup checks (e.g. if typing git, suggest git status)
            if "git".startswith(prefix.lower()):
                candidates = ["git status", "git diff", "git log"]
            elif "docker".startswith(prefix.lower()) or "dc".startswith(prefix.lower()):
                candidates = ["docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.localprod up -d --build --remove-orphans"]
            elif "npm".startswith(prefix.lower()) or "pnpm".startswith(prefix.lower()):
                candidates = ["pnpm build", "pnpm dev", "pnpm test"]
            elif "py".startswith(prefix.lower()) or "python".startswith(prefix.lower()):
                candidates = ["python3 -m venv .venv", "python3 app.py"]
            else:
                return {"prediction": "", "probability": 0.0}

        best_match = candidates[0]
        # Calculate matching ratio as prediction probability
        prob = min(round(len(prefix) / len(best_match), 2), 0.99) if len(best_match) > 0 else 0.0

        # Suggest only the remainder suffix
        suggestion = best_match[len(prefix):] if best_match.lower().startswith(prefix.lower()) else ""

        return {
            "prediction": suggestion,
            "full_command": best_match,
            "probability": prob
        }
