import { ApolloClient, InMemoryCache, createHttpLink, from, split } from '@apollo/client';
import { setContext } from '@apollo/client/link/context';
import { onError } from '@apollo/client/link/error';
import { GraphQLWsLink } from '@apollo/client/link/subscriptions';
import { createClient } from 'graphql-ws';
import { getMainDefinition } from '@apollo/client/utilities';

const makeApolloClient = (token: string | null) => {
  const BYPASS = (typeof window !== 'undefined'
    ? (window as any).ENV?.NEXT_PUBLIC_BYPASS_AUTH === 'true'
    : (process.env.NEXT_PUBLIC_BYPASS_AUTH === 'true'));

  const httpEndpoint = (typeof window !== 'undefined'
    ? (window as any).ENV?.NEXT_PUBLIC_GRAPHQL_ENDPOINT
    : process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT);
  const wsEndpoint = (typeof window !== 'undefined'
    ? (window as any).ENV?.NEXT_PUBLIC_GRAPHQL_WS_ENDPOINT
    : process.env.NEXT_PUBLIC_GRAPHQL_WS_ENDPOINT);

  const resolvedHttp = httpEndpoint || 'http://localhost:8080/graphql';
  const resolvedWs = wsEndpoint
    ? wsEndpoint
    : null; // No WebSocket by default in production

  const httpLink = createHttpLink({ uri: resolvedHttp });

  const errorLink = onError((error: any) => {
    if (error.graphQLErrors) {
      error.graphQLErrors.forEach(({ message, locations, path }: any) => {
        console.error(`GraphQL error: Message: ${message}, Location: ${locations}, Path: ${path}`);
      });
    }

    if (error.networkError) {
      console.error(`Network error: ${error.networkError}`);
    }
  });

  const authLink = setContext((_, { headers }) => {
    let t: string | null = null;
    try {
      t = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : token;
    } catch {
      t = token;
    }
    return {
      headers: {
        ...headers,
        authorization: t ? `Bearer ${t}` : "",
      }
    }
  });

  const wsLink = (typeof window !== 'undefined' && resolvedWs)
    ? new GraphQLWsLink(createClient({
      url: resolvedWs as string,
      connectionParams: () => {
        let t: string | null = null;
        try {
          t = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : token;
        } catch {
          t = token;
        }
        return {
          headers: {
            Authorization: t ? `Bearer ${t}` : "",
          }
        };
      }
    }))
    : null;

  const splitLink = (typeof window !== 'undefined' && wsLink)
    ? split(
      ({ query }) => {
        const definition = getMainDefinition(query);
        return (
          definition.kind === 'OperationDefinition' &&
          definition.operation === 'subscription'
        );
      },
      wsLink,
      from([errorLink, authLink, httpLink])
    )
    : from([errorLink, authLink, httpLink]);

  return new ApolloClient({
    link: splitLink,
    cache: new InMemoryCache(),
  });
};

export const getClient = () => {
	let token: string | null = null;
	try {
		if (typeof window !== 'undefined' && (window as any).localStorage?.getItem) {
			token = (window as any).localStorage.getItem('auth_token');
		} else if (typeof localStorage !== 'undefined' && (localStorage as any).getItem) {
			token = (localStorage as any).getItem('auth_token');
		}
	} catch {
		// ignore and fall through to env-based token
	}
	if (!token && typeof process !== 'undefined') {
		const fromEnv = process.env.ETHERION_TEST_AUTH_TOKEN;
		if (fromEnv && fromEnv.length > 0) {
			token = fromEnv;
		}
	}
	return makeApolloClient(token);
}
