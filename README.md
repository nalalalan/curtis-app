# Curtis Admission Record

Static AO Labs app for `curtis.aolabs.io`.

## Source State

- Curtis Institute of Music official admissions pages reviewed on 2026-05-07.
- Requirements vary by department; instrument and program remain explicit user inputs.
- Stored working state is browser-local in v1.
- DNS required for public custom-domain access: `curtis CNAME nalalalan.github.io`.

## Local Preview

```powershell
python -m http.server 4177
```

Open `http://127.0.0.1:4177/`.
