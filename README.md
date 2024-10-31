# Todo Nanny

A daily planning assistant built with FastAPI, Vue.js, and Tailwind CSS. Uses LLM to help plan your day based on natural language input.

## Features

- Natural language task input
- Automatic daily schedule generation
- Persistent task tracking with localStorage
- Responsive design with Tailwind CSS
- LLM integration (supports Claude and GPT models)

## Local Development

### Prerequisites

- Python 3.13+
- Node.js 20+
- npm or yarn

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/nlbq-fe.git
cd nlbq-fe
```

2. Install Python dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Install Node dependencies:
```bash
npm install
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your LLM API keys and preferences
```

5. Build Tailwind CSS:
```bash
# For development (watch mode)
npm run watch:css

# For production
npm run build:css
```

6. Run the development server:
```bash
uvicorn main:app --reload
```

The application will be available at `http://localhost:8000`

## Docker Deployment

### Building Locally

```bash
docker build -t nlbq-fe .
docker run -p 8000:8000 --env-file .env nlbq-fe
```

### Deploying with Coolify

1. Fork this repository

2. In Coolify:
   - Create a new service
   - Select "Docker" deployment
   - Connect your GitHub repository
   - Configure environment variables:
     - `LLM_MODEL`: Your chosen model (e.g., "claude-3.5-sonnet")
     - `LLM_API_KEY`: Your API key
   - Deploy

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| LLM_MODEL | The LLM model to use | claude-3.5-sonnet |
| LLM_API_KEY | Your API key for the LLM service | sk_... |

## Project Structure

```
.
├── dist/               # Generated CSS (gitignored)
├── src/               
│   └── input.css      # Tailwind CSS source
├── static/            # Static assets
├── index.html         # Main frontend template
├── main.py           # FastAPI application
├── Dockerfile        # Docker configuration
└── requirements.txt  # Python dependencies
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source and available under the MIT License.