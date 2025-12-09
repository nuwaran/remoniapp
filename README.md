# REMONI - Remote Health Monitoring System

A web-based health monitoring application that provides real-time patient vital signs monitoring and AI-powered medical assistance.

## Features

- Real-time vital signs monitoring (Heart Rate, SpO2, Blood Pressure, Temperature)
- AI-powered virtual nurse assistant using GPT
- Data visualization with automatic plot generation
- Fall detection alerts
- Integration with wearable devices and Raspberry Pi health monitors

## Tech Stack

- **Backend**: Flask, SocketIO
- **AI**: OpenAI GPT-3.5/4
- **Data Processing**: Pandas, NumPy
- **Visualization**: Matplotlib
- **Cloud Storage**: AWS S3
- **Frontend**: HTML, CSS, JavaScript

## Installation

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/nuwaran/Remoni_Web_APP.git
cd Remoni_Web_APP
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

5. Run the application:
```bash
python app.py
```

Visit `http://localhost:5001` in your browser.

### Deploy to PythonAnywhere

1. **Upload files** to PythonAnywhere using Git:
```bash
git clone https://github.com/nuwaran/Remoni_Web_APP.git
```

2. **Create virtual environment**:
```bash
mkvirtualenv --python=/usr/bin/python3.10 remoni-env
pip install -r requirements.txt
```

3. **Configure Web App**:
   - Go to Web tab
   - Add new web app
   - Select "Manual configuration" with Python 3.10
   - Set source code: `/home/yourusername/Remoni_Web_APP`
   - Set WSGI file: `/home/yourusername/Remoni_Web_APP/wsgi.py`
   - Set virtualenv: `/home/yourusername/.virtualenvs/remoni-env`

4. **Set environment variables** in WSGI file or Web tab

5. **Create data directories**:
```bash
mkdir -p static/local_data/show_data
```

6. **Reload** the web app

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

- `OPENAI_KEY`: Your OpenAI API key
- `S3_KEY_ID`: AWS access key ID
- `S3_SECRET_KEY`: AWS secret access key
- `S3_BUCKET_NAME`: S3 bucket name
- `RASPBERRY_PI_URL`: URL of your Raspberry Pi health monitor

## API Endpoints

- `GET /` - Main chat interface
- `POST /chat` - Process user queries
- `POST /sensor_data` - Receive sensor data from wearables
- `GET /api/latest_vitals_from_pi` - Get latest vitals from Raspberry Pi
- `GET /api/fall_alerts` - Get fall detection alerts
- `GET /debug_data` - Debug endpoint for data inspection

## Usage

### Chat Interface

Ask questions like:
- "What is the current heart rate of patient 00001?"
- "Show me a plot of heart rate for the last 10 minutes"
- "What are the latest vital signs?"

### Sensor Integration

The system accepts data from:
- Smartwatches (via `/sensor_data` endpoint)
- Raspberry Pi health monitors (via WebSocket)

## Project Structure

```
Remoni_Web_APP/
├── app.py                      # Main Flask application
├── wsgi.py                     # WSGI entry point
├── nlp_engine.py              # NLP processing engine
├── request_to_openai.py       # OpenAI API integration
├── utils.py                    # Utility functions
├── config.py                   # Configuration
├── config_nlp_engine.py       # NLP configuration
├── requirements.txt            # Python dependencies
├── templates/
│   └── doctor.html            # Main chat interface
├── static/
│   ├── css/
│   │   └── doctor.css        # Styles
│   ├── js/
│   │   └── doctor.js         # Frontend logic
│   └── images/
│       └── nurse.png         # Logo
└── .env.example               # Environment variables template
```

## Security Notes

**Important**: Never commit your `.env` file with real credentials to Git!

- Always use `.env.example` for templates
- Store sensitive credentials in environment variables
- Regenerate API keys if accidentally exposed
- Use PythonAnywhere's environment variable settings for production

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.

## Support

For issues and questions, please open an issue on GitHub.

## Acknowledgments

- OpenAI for GPT models
- Flask and SocketIO communities
- PythonAnywhere for hosting platform
