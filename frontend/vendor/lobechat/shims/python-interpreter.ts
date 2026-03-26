// Minimal types to satisfy '@lobechat/python-interpreter' imports
export type PythonResult = {
  success: boolean;
  stdout?: string;
  stderr?: string;
  images?: string[];
  html?: string;
  errorMessage?: string;
};
