import express from 'express';
import { Application, Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import connectDB from './config/db';
import { errorHandler, notFound } from './middlewares/errorMiddleware';
import roomRoutes from './routes/roomRoutes';
import userRoutes from './routes/userRoutes';
import bookingRoutes from './routes/bookingRoutes';
import uploadRoutes from './routes/uploadRoutes';

dotenv.config();
const app: Application = express();
app.use(cors());
app.use(express.json());
app.use('/uploads', express.static(path.join(__dirname, '../uploads')));

app.get('/api', (req: Request, res: Response) => {
  res.status(200).json({ message: 'Welcome to Hotel Booking App' });
});
app.get('/api/health', (req: Request, res: Response) => {
  res.status(200).json({ status: 'ok' });
});
app.use('/api/rooms', roomRoutes);
app.use('/api/users', userRoutes);
app.use('/api/bookings', bookingRoutes);
app.use('/api/uploads', uploadRoutes);

app.get('/api/config/paypal', (req: Request, res: Response) => {
  const clientId = process.env.PAYPAL_CLIENT_ID;
  if (!clientId) {
    res.status(503).json({ message: 'PayPal is not configured. Set PAYPAL_CLIENT_ID for checkout.' });
    return;
  }
  res.status(200).send(clientId);
});

app.use(notFound);
app.use(errorHandler);

const PORT = process.env.PORT || 5000;

const startServer = async (): Promise<void> => {
  try {
    if (!process.env.JWT_SECRET || process.env.JWT_SECRET === 'replace-with-a-long-random-development-secret') {
      throw new Error('Set a unique JWT_SECRET in .env (see .env.example).');
    }
    await connectDB();
    app.listen(PORT, () => console.log(`Server is running on PORT ${PORT}`));
  } catch (error: any) {
    console.error('Backend startup failed:', error.message);
    process.exit(1);
  }
};

startServer();
