import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Text, Button, Input, Spinner, tokens, makeStyles, DataGrid, DataGridBody, DataGridCell, DataGridHeader, DataGridHeaderCell, DataGridRow, createTableColumn, TableCellLayout } from "@fluentui/react-components";
import { useState } from "react";
import { api } from "../../hooks/useApi";
import type { User, ClassSummaryEntry } from "../../types";

const useStyles = makeStyles({
  root: { padding: tokens.spacingVerticalL },
  enroll: { display: "flex", gap: tokens.spacingHorizontalS, marginBottom: tokens.spacingVerticalM },
});

export default function ClassDetailPage() {
  const { classId } = useParams<{ classId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [upn, setUpn] = useState("");

  const { data: summary, isLoading } = useQuery<ClassSummaryEntry[]>({
    queryKey: ["summary", classId],
    queryFn: () => api.get(`/records/${classId}/summary`),
  });

  const enrollMutation = useMutation({
    mutationFn: () => api.post(`/classes/${classId}/enroll`, { student_upn: upn }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["summary", classId] });
      setUpn("");
    },
  });

  const columns = [
    createTableColumn<ClassSummaryEntry>({
      columnId: "name",
      renderHeaderCell: () => "Name",
      renderCell: (item) => <TableCellLayout>{item.display_name}</TableCellLayout>,
    }),
    createTableColumn<ClassSummaryEntry>({
      columnId: "note",
      renderHeaderCell: () => "Note",
      renderCell: (item) => <TableCellLayout><strong>{item.grade.note}</strong> ({item.grade.prozent}%)</TableCellLayout>,
    }),
    createTableColumn<ClassSummaryEntry>({
      columnId: "actions",
      renderHeaderCell: () => "",
      renderCell: (item) => (
        <TableCellLayout>
          <Button size="small" onClick={() => navigate(`/teacher/classes/${classId}/students/${item.student_id}`)}>
            Details
          </Button>
        </TableCellLayout>
      ),
    }),
  ];

  return (
    <div className={useStyles().root}>
      <Button appearance="subtle" onClick={() => navigate("/teacher/classes")}>← Zurück</Button>
      <Text size={700} weight="semibold" block>Klasse</Text>

      <div className={useStyles().enroll}>
        <Input
          placeholder="student@schule.de"
          value={upn}
          onChange={(_, d) => setUpn(d.value)}
        />
        <Button onClick={() => enrollMutation.mutate()} disabled={!upn}>Schüler:in hinzufügen</Button>
        <Button onClick={() => navigate(`/teacher/classes/${classId}/tests`)}>Tests anzeigen</Button>
      </div>

      {isLoading && <Spinner />}
      {summary && (
        <DataGrid items={summary} columns={columns} getRowId={(item) => item.student_id}>
          <DataGridHeader>
            <DataGridRow>{({ renderHeaderCell }) => <DataGridHeaderCell>{renderHeaderCell()}</DataGridHeaderCell>}</DataGridRow>
          </DataGridHeader>
          <DataGridBody<ClassSummaryEntry>>
            {({ item, rowId }) => (
              <DataGridRow<ClassSummaryEntry> key={rowId}>
                {({ renderCell }) => <DataGridCell>{renderCell(item)}</DataGridCell>}
              </DataGridRow>
            )}
          </DataGridBody>
        </DataGrid>
      )}
    </div>
  );
}
