import { useQuery } from "@tanstack/react-query";
import { Text, Spinner, tokens, makeStyles, Link } from "@fluentui/react-components";
import { api } from "../../hooks/useApi";
import type { Appointment } from "../../types";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 700 },
  iframe: { width: "100%", height: 600, border: "none", marginTop: 16 },
});

interface BookingsConfig {
  use_api: boolean;
  page_url: string;
}

export default function AppointmentsPage() {
  const styles = useStyles();

  const { data: config } = useQuery<BookingsConfig>({
    queryKey: ["bookings-config"],
    queryFn: () => api.get("/bookings/page-url"),
  });

  const { data: appointments, isLoading } = useQuery<Appointment[]>({
    queryKey: ["appointments", "me"],
    queryFn: () => api.get("/bookings/me"),
  });

  return (
    <div className={styles.root}>
      <Text size={700} weight="semibold">Prüfungstermin buchen</Text>

      {!config?.use_api && config?.page_url && (
        <>
          <Text block>Buche deinen Termin direkt über Microsoft Bookings:</Text>
          <Link href={config.page_url} target="_blank">Buchungsseite öffnen</Link>
          <iframe
            src={config.page_url}
            className={styles.iframe}
            title="Microsoft Bookings"
            allow="camera; microphone"
          />
        </>
      )}

      {isLoading && <Spinner />}

      {appointments && appointments.length > 0 && (
        <>
          <Text size={500} weight="semibold" block style={{ marginTop: 24 }}>
            Meine Termine
          </Text>
          {appointments.map((a) => (
            <div key={a.id} style={{ padding: 8, borderBottom: "1px solid #eee" }}>
              <Text>
                {a.scheduled_start
                  ? new Date(a.scheduled_start).toLocaleString("de-DE")
                  : "Termin ausstehend"}
                {" — "}
                <strong>{a.status}</strong>
              </Text>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
