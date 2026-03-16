import { Checkbox, Text, tokens, makeStyles } from "@fluentui/react-components";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../hooks/useApi";
import type { Competency, Record } from "../../types";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
});

interface Props {
  competencies: Competency[];
  records: Record[];
  classId: string;
  studentId: string;
}

export default function IbKTeacherPanel({ competencies, records, classId, studentId }: Props) {
  const styles = useStyles();
  const queryClient = useQueryClient();
  const recordMap = new Map(records.map((r) => [r.competency_id, r]));

  const mutation = useMutation({
    mutationFn: ({ competencyId, achieved }: { competencyId: string; achieved: boolean }) =>
      api.put(`/records/${classId}/${studentId}/${competencyId}`, { achieved }),
    onMutate: async ({ competencyId, achieved }) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ["records", classId, studentId] });
      const prev = queryClient.getQueryData(["records", classId, studentId]);
      queryClient.setQueryData(["records", classId, studentId], (old: any) => ({
        ...old,
        records: old?.records?.map((r: Record) =>
          r.competency_id === competencyId ? { ...r, achieved } : r
        ) ?? [],
      }));
      return { prev };
    },
    onError: (_err, _vars, context: any) => {
      if (context?.prev) {
        queryClient.setQueryData(["records", classId, studentId], context.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["records", classId, studentId] });
    },
  });

  return (
    <div className={styles.root}>
      <Text size={500} weight="semibold">ibK</Text>
      {competencies.map((c) => {
        const achieved = recordMap.get(c.id)?.achieved ?? false;
        return (
          <Checkbox
            key={c.id}
            label={c.name}
            checked={achieved}
            onChange={(_, data) =>
              mutation.mutate({ competencyId: c.id, achieved: data.checked === true })
            }
          />
        );
      })}
    </div>
  );
}
