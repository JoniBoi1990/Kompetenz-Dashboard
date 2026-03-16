import { useQuery } from "@tanstack/react-query";
import { Text, Button, Badge, Spinner, tokens, makeStyles, Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from "@fluentui/react-components";
import { useState } from "react";
import { api } from "../../hooks/useApi";
import type { Class, GeneratedTest } from "../../types";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL, maxWidth: 900 },
});

export default function TestHistoryPage() {
  const styles = useStyles();
  const [classId, setClassId] = useState<string>("");

  const { data: classes } = useQuery<Class[]>({
    queryKey: ["classes"],
    queryFn: () => api.get("/classes"),
    onSuccess: (data: Class[]) => { if (data.length && !classId) setClassId(data[0].id); },
  } as any);

  const { data: tests, isLoading } = useQuery<GeneratedTest[]>({
    queryKey: ["tests", "me", classId],
    queryFn: () => api.get(`/tests/me/${classId}`),
    enabled: !!classId,
    refetchInterval: (data) => data?.some((t) => !t.pdf_generated_at && !t.pdf_error) ? 3000 : false,
  });

  const downloadPdf = (testId: string) => {
    window.open(`/api/tests/${testId}/pdf`, "_blank");
  };

  return (
    <div className={styles.root}>
      <Text size={700} weight="semibold">Meine Tests</Text>

      {isLoading && <Spinner />}

      {tests && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHeaderCell>Erstellt</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Kompetenzen</TableHeaderCell>
              <TableHeaderCell>Download</TableHeaderCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tests.map((t) => (
              <TableRow key={t.id}>
                <TableCell>{new Date(t.created_at).toLocaleDateString("de-DE")}</TableCell>
                <TableCell>
                  {t.pdf_error ? (
                    <Badge color="danger">Fehler</Badge>
                  ) : t.pdf_generated_at ? (
                    <Badge color="success">Fertig</Badge>
                  ) : (
                    <Badge color="warning">Wird generiert...</Badge>
                  )}
                </TableCell>
                <TableCell>{t.competency_ids.length} Kompetenzen</TableCell>
                <TableCell>
                  {t.pdf_generated_at && (
                    <Button size="small" onClick={() => downloadPdf(t.id)}>PDF</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
