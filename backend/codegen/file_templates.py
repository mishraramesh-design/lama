"""Per-file-type instructions injected into codegen prompts."""

FILE_TYPE_INSTRUCTIONS = {
    "model": {
        "nodejs": "Generate a Sequelize ORM model file. Include all columns from the DDL, associations, validations.",
        "python": "Generate a SQLAlchemy 2.0 ORM model. Include all columns, relationships, validators.",
        "java": "Generate a JPA Entity class with fields, relationships, validation annotations.",
        "go": "Generate a GORM model struct with all fields, tags, associations.",
    },
    "route": {
        "nodejs": "Generate an Express Router with CRUD + custom endpoints. Zod validation. Async/await + try/catch. JSDoc.",
        "python": "Generate a FastAPI router. Pydantic models for request/response. Docstrings.",
        "java": "Generate a Spring Boot @RestController with @Valid + ResponseEntity returns.",
        "go": "Generate a Gin route handler. Binding, validation, error handling.",
    },
    "service": {
        "nodejs": "Generate a Service class (business logic). No direct DB calls — use the model layer. JSDoc.",
        "python": "Generate a Service class. Inject repository via constructor. Docstrings.",
        "java": "Generate a @Service class. @Transactional where needed. Javadoc.",
        "go": "Generate a service struct with interface. Document every method.",
    },
    "middleware": {
        "nodejs": "Express middleware: JWT verify, role check, request logging, rate limiting.",
        "python": "FastAPI dependencies + middleware: JWT auth, role check, logging.",
        "java": "Spring Security configuration + filter chain.",
        "go": "Gin middleware functions.",
    },
    "dockerfile": {
        "nodejs": "Multi-stage Dockerfile: build (node:20-alpine) + production (node:20-alpine, non-root, healthcheck, ENV port).",
        "python": "Multi-stage Dockerfile: builder (python:3.12-slim) + runtime (python:3.12-slim, non-root, uvicorn entrypoint, healthcheck).",
        "java": "Multi-stage Dockerfile: build (eclipse-temurin:21-jdk-alpine) + runtime (eclipse-temurin:21-jre-alpine, JVM container flags, healthcheck).",
        "go": "Multi-stage Dockerfile: build (golang:1.22-alpine) + runtime (alpine:latest, binary only, non-root, healthcheck).",
    },
    "test": {
        "nodejs": "Jest tests: service-layer unit tests with mocked DB; route integration tests with supertest. Cover happy + error + edge.",
        "python": "Pytest tests with fixtures. Unit (mocked DB) + integration (TestClient).",
        "java": "JUnit 5 + Mockito. @Mock unit + @WebMvcTest slice tests.",
        "go": "Testify table-driven tests. Mock interfaces. HTTP handler tests.",
    },
    "config": {
        "nodejs": ".env.example + config/database.js + config/app.js (cors, rate-limit, compression).",
        "python": ".env.example + config/settings.py (Pydantic BaseSettings) + config/database.py (async engine).",
        "java": "application.yml + application-test.yml + DatabaseConfig.java + SecurityConfig.java.",
        "go": "config/config.go (viper) + .env.example.",
    },
    "compose": {
        "any": "docker-compose.yml linking all services + PostgreSQL + Redis. Healthchecks. Named volumes for DB. Environment via .env file.",
    },
    "ci": {
        "any": "GitHub Actions workflow: install, lint, test, build matrix per service. Run on push + pull_request.",
    },
}


FRONTEND_COMPONENT_INSTRUCTIONS = {
    "page": "Full page: React Query useQuery/useMutation, loading skeleton, error boundary, empty state, pagination, modal create/edit, role-based UI, breadcrumbs.",
    "form": "React Hook Form + Zod schema. Field-level errors. Submit + loading state. A11y attrs.",
    "table": "Sortable, filterable, paginated data table with row actions and bulk select.",
    "layout": "Sidebar nav + breadcrumbs + user menu + notifications + responsive mobile menu.",
    "api_client": "Typed axios client. One function per endpoint. TypeScript request/response interfaces. Error handling. Auth header injection.",
    "store": "Zustand store: typed state, actions, selectors. Persist auth to localStorage.",
    "route_config": "React Router v6 lazy-loaded routes. Protected routes. Role-based guards.",
    "scaffold": "package.json + vite.config.ts + tsconfig.json + index.html + main.tsx for a fresh Vite + React + TS app.",
}


def get_file_instruction(file_type: str, backend_lang: str) -> str:
    bucket = FILE_TYPE_INSTRUCTIONS.get(file_type, {})
    return bucket.get(backend_lang) or bucket.get("any") or "Generate appropriate content for this file."


def get_frontend_instruction(component_type: str) -> str:
    return FRONTEND_COMPONENT_INSTRUCTIONS.get(component_type, "Generate the React component for this file path.")
