"""Research request forecasts and the resources held for final evidence review."""
from dataclasses import dataclass


@dataclass
class ContextForecast:
    """Share the last observed native context across policy and review calls."""
    retained_units: int = 0

    def observe(self, records, *, context_units=None):
        # Usage is recorded separately by the runtime. The most recent request
        # supplies the forecast base; summing usage would count history twice.
        if records:
            self.retained_units = (context_units if isinstance(context_units, int) and context_units > 0
                                   else sum(r.input_tokens + r.output_tokens for r in records))

    def request(self, prompt_bytes, schema_bytes, output_units, *, retained=False,
                preceding_units=0):
        incoming = prompt_bytes + schema_bytes + output_units
        return incoming + (self.retained_units + preceding_units if retained else 0)


def closing_envelope(request_units, correction_units, attempts, *, retained=False):
    """Forecast the allowed review attempts, including their retained history."""
    total = request_units
    previous = request_units
    for _ in range(1, attempts):
        current = correction_units + (previous if retained else 0)
        total += current
        previous = current
    return total
