import { TopBar } from './TopBar'

type LoadingStateProps = {
  message: string
}

export function LoadingState({ message }: LoadingStateProps) {
  return (
    <div className="flex flex-col h-screen w-screen bg-ops-bg text-ops-text overflow-hidden">
      <TopBar />
      <main className="flex-1 flex overflow-hidden">
        <section className="flex-1 flex items-center justify-center bg-ops-panel border border-ops-border/20 m-4 rounded-xl">
          <p className="text-ops-muted text-sm flex items-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-ops-green border-t-transparent animate-spin inline-block"></span>
            {message}
          </p>
        </section>
      </main>
    </div>
  )
}
