import mongoose from 'mongoose';

const connectDB = async (): Promise<void> => {
  const uri = process.env.MONGO_URI;
  if (!uri) {
    throw new Error('MONGO_URI is missing. Copy .env.example to .env and set the local MongoDB URI.');
  }
  await mongoose.connect(uri);
  console.log('Database is connected');
};

export default connectDB;
