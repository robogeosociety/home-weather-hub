import { useEffect } from 'react';
import { motion } from 'motion/react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchSnapshot, openLiveSocket } from './api/client';
import { Dashboard } from './components/Dashboard';
import { Ticker } from './components/Ticker';
import { Toolbar } from './components/Toolbar';
import { TVRoute } from './components/TVRoute';
import { useLayout } from './state/layout';
import { useLive } from './state/live';
import { useSettings } from './state/settings';

function isTvMode(): boolean {
  return new URLSearchParams(location.search).get('tv') === '1';
}

export default function App() {
  const editMode = useSettings((s) => s.editMode);
  const loadLayout = useLayout((s) => s.load);
  const applySnapshot = useLive((s) => s.applySnapshot);
  const applyEvent = useLive((s) => s.applyEvent);
  const queryClient = useQueryClient();

  // Initial snapshot via REST so the dashboard paints instantly on load.
  const snapQ = useQuery({
    queryKey: ['snapshot'],
    queryFn: fetchSnapshot,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (snapQ.data) applySnapshot(snapQ.data);
  }, [snapQ.data, applySnapshot]);

  // Live event stream over WebSocket.
  useEffect(() => {
    const close = openLiveSocket((msg) => {
      if (msg.type === 'snapshot') {
        applySnapshot(msg.data);
      } else if (msg.type === 'event') {
        applyEvent(msg.data as unknown as Parameters<typeof applyEvent>[0]);
        // History queries should refresh on new data.
        queryClient.invalidateQueries({ queryKey: ['history'] });
        if (msg.data.type === 'evt_strike') {
          queryClient.invalidateQueries({ queryKey: ['strikes'] });
        }
      }
    });
    return close;
  }, [applySnapshot, applyEvent, queryClient]);

  // Hydrate persisted layouts.
  useEffect(() => {
    void loadLayout();
  }, [loadLayout]);

  if (isTvMode()) {
    return (
      <>
        <div className="twc-grain" />
        <div className="twc-atmosphere" />
        <TVRoute />
      </>
    );
  }

  return (
    <>
      <div className="twc-grain" />
      <div className="twc-atmosphere" />
      <motion.div
        className="twc-app"
        data-edit={editMode}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
      >
        <Toolbar />
        <Dashboard />
        <Ticker />
      </motion.div>
    </>
  );
}
