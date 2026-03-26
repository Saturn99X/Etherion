 import type { RepositoryAsset } from './repository';
 import { getAsset, listAssets } from './repository';

 export type KnowledgeItem = RepositoryAsset;

 export interface FileKnowledgeSource {
   kind: 'file';
   file: File;
 }

 export interface UrlKnowledgeSource {
   kind: 'url';
   url: string;
 }

 export type KnowledgeSource = FileKnowledgeSource | UrlKnowledgeSource;

 export interface ListKnowledgeItemsOptions {
   limit?: number;
   jobId?: string | null;
   includeDownload?: boolean;
 }

 export async function ingestToKnowledgeBase(_source: KnowledgeSource): Promise<never> {
   throw new Error(
     'KnowledgeBaseBridge: ingestToKnowledgeBase is not implemented on the frontend; ingestion is triggered via backend jobs or connectors.',
   );
 }

 export async function listKnowledgeItems(
   options?: number | ListKnowledgeItemsOptions,
 ): Promise<KnowledgeItem[]> {
   const normalized: ListKnowledgeItemsOptions =
     typeof options === 'number' || typeof options === 'undefined'
       ? {
           limit: typeof options === 'number' ? options : undefined,
           includeDownload: false,
         }
       : options;

   const { limit = 50, jobId = null, includeDownload = false } = normalized;

   return listAssets({ limit, jobId, includeDownload });
 }

 export async function getKnowledgeItemDetails(id: string): Promise<KnowledgeItem | null> {
   const trimmed = (id ?? '').trim();
   if (!trimmed) {
     throw new Error('id is required to load knowledge item details');
   }

   return getAsset(trimmed);
 }
