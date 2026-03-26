import { create } from 'zustand'

export type Team = { id: string; name: string }

interface TeamState {
  teams: Team[]
  selectedTeamId: string | null
  setSelectedTeamId: (id: string | null) => void
  setTeams: (teams: Team[]) => void
}

export const useTeamStore = create<TeamState>((set) => ({
  teams: [
    { id: 'orchestrator', name: 'Team Orchestrator' },
    { id: 'research', name: 'Research Team' },
    { id: 'engineering', name: 'Engineering Team' },
  ],
  selectedTeamId: 'orchestrator',
  setSelectedTeamId: (id) => set({ selectedTeamId: id }),
  setTeams: (teams) => set({ teams }),
}))
