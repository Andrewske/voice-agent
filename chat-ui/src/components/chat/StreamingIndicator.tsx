export function StreamingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[85%]">
        <div className="rounded-2xl px-4 py-3 bg-slate-800 border border-slate-700">
          <div className="flex gap-1">
            <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" />
          </div>
        </div>
      </div>
    </div>
  )
}
