# Hotel Booking (local development)

MERN hotel-booking application using TypeScript, React/Redux, Express and MongoDB.

## Requirements
- Node.js and npm (this is an older React Scripts 5 project; Node.js 18 LTS is a practical first choice)
- Local MongoDB listening at `127.0.0.1:27017`

## Configure
1. Copy `.env.example` to `.env` in this project root.
2. Set `MONGO_URI` to your local database (default example: `mongodb://127.0.0.1:27017/hotel_booking`).
3. Replace the placeholder `JWT_SECRET` with a long, unique random string. Keep `.env` out of Git.
4. (Optional) Set a **PayPal sandbox** `PAYPAL_CLIENT_ID` to test checkout. Without it, room browsing can still work but payment checkout cannot.

On Windows PowerShell: `Copy-Item .env.example .env`
On macOS/Linux: `cp .env.example .env`

## Install
From the project root:

```sh
npm install
cd frontend
npm install
cd ..
```

## Run
In two terminals from the project root:

```sh
npm run server
```

```sh
npm run client
```

Backend: http://localhost:5000/api/health  
Frontend: http://localhost:3000  
The React dev proxy forwards `/api` and `/uploads` to localhost:5000. Start the backend first.
