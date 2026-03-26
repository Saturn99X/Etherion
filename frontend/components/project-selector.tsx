"use client";

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Plus, FolderKanban } from 'lucide-react';
import { ProjectService, type Project } from '@/lib/services/project-service';
import { useToast } from '@/hooks/use-toast';

// Mock toast hook for now if it doesn't exist
const useToastMock = () => ({
  toast: ({ title, description, variant }: { title: string; description: string; variant?: string }) => {
    console.log(`Toast: ${title} - ${description} (${variant})`);
  }
});

interface ProjectSelectorProps {
  selectedProjectId?: number;
  onProjectSelect?: (project: Project | null) => void;
  className?: string;
}

export function ProjectSelector({ selectedProjectId, onProjectSelect, className }: ProjectSelectorProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasAttemptedLoad, setHasAttemptedLoad] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const { toast } = useToast() || useToastMock();

  const loadProjects = async () => {
    setIsLoading(true);
    try {
      const fetchedProjects = await ProjectService.getProjects();
      setProjects(fetchedProjects);
      setHasAttemptedLoad(true);

      // Auto-select first project if none selected
      if (!selectedProjectId && fetchedProjects.length > 0) {
        onProjectSelect?.(fetchedProjects[0]);
      }
    } catch (error) {
      console.error('Failed to load projects:', error);
      setHasAttemptedLoad(true);
      toast({
        title: "Error",
        description: "Failed to load projects. Backend may not be running.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // CRITICAL FIX: Only load once on mount, prevent infinite retry loop
  useEffect(() => {
    if (!hasAttemptedLoad) {
      loadProjects();
    }
  }, [hasAttemptedLoad]);

  const handleProjectSelect = (projectId: string) => {
    const project = projects.find(p => p.id === parseInt(projectId));
    onProjectSelect?.(project || null);
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;

    setIsCreating(true);
    try {
      const newProject = await ProjectService.createProject({
        name: newProjectName.trim(),
        description: newProjectDescription.trim(),
      });

      setProjects(prev => [...prev, newProject]);
      setNewProjectName('');
      setNewProjectDescription('');
      setIsCreateDialogOpen(false);

      // Auto-select the new project
      onProjectSelect?.(newProject);

      toast({
        title: "Success",
        description: "Project created successfully",
      });
    } catch (error) {
      console.error('Failed to create project:', error);
      toast({
        title: "Error",
        description: "Failed to create project",
        variant: "destructive",
      });
    } finally {
      setIsCreating(false);
    }
  };

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <FolderKanban className="h-4 w-4 text-white/70" />

      <Select
        value={selectedProjectId?.toString() || ''}
        onValueChange={handleProjectSelect}
        disabled={isLoading}
      >
        <SelectTrigger className="glass border-border text-foreground min-w-[200px]">
          <SelectValue placeholder={isLoading ? "Loading projects..." : "Select project"} />
        </SelectTrigger>
        <SelectContent className="glass-strong border-border">
          {projects.map((project) => (
            <SelectItem key={project.id} value={project.id.toString()}>
              {project.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="glass-button hover:glow-purple transition-all duration-300"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </DialogTrigger>
        <DialogContent className="glass-strong border-border">
          <DialogHeader>
            <DialogTitle className="text-white">Create New Project</DialogTitle>
            <DialogDescription className="text-white/70">
              Create a new project to organize your goals and conversations.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="project-name" className="text-white">Project Name</Label>
              <Input
                id="project-name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="Enter project name"
                className="glass border-border text-white"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="project-description" className="text-white">Description (Optional)</Label>
              <Textarea
                id="project-description"
                value={newProjectDescription}
                onChange={(e) => setNewProjectDescription(e.target.value)}
                placeholder="Enter project description"
                className="glass border-border text-white"
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
              className="glass-button"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateProject}
              disabled={!newProjectName.trim() || isCreating}
              className="glass-button hover:glow-purple transition-all duration-300"
            >
              {isCreating ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                  Creating...
                </>
              ) : (
                'Create Project'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
