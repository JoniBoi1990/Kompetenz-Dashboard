import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Text, Button, Badge, Spinner, Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow, tokens, makeStyles } from "@fluentui/react-components";
import { api } from "../../hooks/useApi";
import type { GeneratedTest } from "../../types";

const useStyles = makeStyles({ root: { padding: tokens.spacingVerticalL } });

export default function TeacherTestsPage() {
  const { classId } = useParams<{ classId: string }>();
  const navigate = useNavigate();

  const { data: tests, isLoading } = useQuery<GeneratedTest[]>({
    queryKey: ["tests", "class", classId],
    queryFn: () => api.get(`/tests/class/${classId}`),
  });

  return (
    <div className={useStyles().root}>
      <Button appearance="subtle" onClick={() => navigate(`/teacher/classes/${classId}`)}>← Zurück</Button>
      <Text size={700} weight="semibold" block>Generierte Tests</Text>

      {isLoading && <Spinner />}
      {tests && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHeaderCell>Schüler:in</TableHeaderCell>
              <TableHeaderCell>Erstellt</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>PDF</TableHeaderCell>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tests.map((t) => (
              <TableRow key={t.id}>
                <TableCell>{t.student_id}</TableCell>
                <TableCell>{new Date(t.created_at).toLocaleDateString("de-DE")}</TableCell>
                <TableCell>
                  {t.pdf_error ? <Badge color="danger">Fehler</Badge>
                    : t.pdf_generated_at ? <Badge color="success">Fertig</Badge>
                    : <Badge color="warning">Ausstehend</Badge>}
                </TableCell>
                <TableCell>
                  {t.pdf_generated_at && (
                    <Button size="small" onClick={() => window.open(`/api/tests/${t.id}/pdf`, "_blank")}>
                      PDF
                    </Button>
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
