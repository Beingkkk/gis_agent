import { useRef, useEffect, useCallback } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage: (data: string) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(
    (url: string, options: Omit<UseWebSocketOptions, 'url'>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close()
      }

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        options.onOpen?.()
      }

      ws.onmessage = (event) => {
        options.onMessage(event.data)
      }

      ws.onclose = () => {
        options.onClose?.()
      }

      ws.onerror = (error) => {
        options.onError?.(error)
      }
    },
    []
  )

  const send = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message)
    }
  }, [])

  const close = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      close()
    }
  }, [close])

  return { connect, send, close }
}
