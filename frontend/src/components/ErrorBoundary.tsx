import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  /** Shown in the fallback so the user knows which widget failed. */
  name: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render errors from one widget so a bad payload never blanks the whole page.
 * The widget re-renders from scratch when the user clicks Retry or the next poll changes its props.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.name}] render failed`, error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.children !== this.props.children) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="rounded-xl border border-red-500/40 bg-ink-900/80 p-4 text-sm text-red-200" aria-label={this.props.name}>
        <p className="font-medium">{this.props.name} could not render</p>
        <p className="mt-1 break-words text-xs opacity-80">{this.state.error.message}</p>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="mt-2 rounded border border-red-400/40 px-2 py-1 text-xs hover:bg-red-500/20"
        >
          Retry
        </button>
      </section>
    );
  }
}
