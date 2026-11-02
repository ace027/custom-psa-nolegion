import { Component, ReactNode } from "react";

export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div role="alert" className="space-y-2 rounded border border-red-200 bg-red-50 p-4 text-red-800">
        <h2 className="font-semibold">Something went wrong</h2>
        <p className="text-sm">{error.message}</p>
        <button type="button" className="rounded border border-red-300 bg-white px-3 py-1 text-sm" onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
