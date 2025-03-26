#include <stdio.h>

extern struct rtpkt {
  int sourceid;       /* id of sending router sending this pkt */
  int destid;         /* id of router to which pkt being sent 
                         (must be an immediate neighbor) */
  int mincost[4];    /* min cost to node 0 ... 3 */
  };

extern int TRACE;
extern int YES;
extern int NO;
extern float clocktime;
int connectcosts0[4] = { 0,  1,  3, 7 };

struct distance_table 
{
  int costs[4][4];
} dt0;


/* students to write the following two routines, and maybe some others */

void rtinit0() 
{
  for (int i = 0; i < 4; i++)
    {
        for (int j = 0; j < 4; j++)
        {
            dt0.costs[i][j] = 999;
        }
    }

    for(int i=0; i<4; i++){
        dt0.costs[i][i] = connectcosts0[i];
    }

    dt0.costs[0][1] = dt0.costs[1][0] = 1;
    dt0.costs[0][2] = dt0.costs[2][0] = 3;
    dt0.costs[0][3] = dt0.costs[3][0] = 7;

    struct rtpkt p0;
    p0.sourceid = 0;
    p0.mincost[0] = dt0.costs[0][0];
    p0.mincost[1] = dt0.costs[0][1];
    p0.mincost[2] = dt0.costs[0][2];
    p0.mincost[3] = dt0.costs[0][3];

    p0.destid = 1;
    tolayer2(p0);
    p0.destid = 2;
    tolayer2(p0);
    p0.destid = 3;
    tolayer2(p0);
    printf("init 0 clocktime = %f\n", clocktime);
    printf("init distance table of node 0 :\n");
    printdt0(&dt0);
}


void rtupdate0(struct rtpkt *rcvdpkt)
{
    int source = rcvdpkt->sourceid;
    if (source < 0 || source >= 4)
        return;

    int changed = 0;

    for (int dest = 0; dest < 4; dest++) {
        int newcost = connectcosts0[source] + rcvdpkt->mincost[dest];
        if (newcost > 999) newcost = 999;
        if(newcost < dt0.costs[source][dest])
            changed = 1;
        dt0.costs[source][dest] = newcost;
    }

    for (int dest = 0; dest < 4; dest++) {
        int oldcost = dt0.costs[0][dest]; 
        int best = 999;

        for (int via = 0; via < 4; via++) {
            if (dt0.costs[via][dest] < best) {
                best = dt0.costs[via][dest];
            }
        }

        if (best < oldcost) {
            dt0.costs[0][dest] = best;
            changed = 1;
        }
    }
    
    if (changed) {
        struct rtpkt packet;
        packet.sourceid = 0;
        for (int i = 0; i < 4; ++i)
            packet.mincost[i] = dt0.costs[0][i];
        packet.destid = 1;
        tolayer2(packet);
        packet.destid = 2;
        tolayer2(packet);
        packet.destid = 3;
        tolayer2(packet);
        printf("update table 0\n");
        printdt0(&dt0);
    } else {
        printf("No Update in node 0\n");
    }
}


printdt0(dtptr)
  struct distance_table *dtptr;
  
{
  printf("                via     \n");
  printf("   D0 |    1     2    3 \n");
  printf("  ----|-----------------\n");
  printf("     1|  %3d   %3d   %3d\n",dtptr->costs[1][1],
	 dtptr->costs[2][1],dtptr->costs[3][1]);
  printf("dest 2|  %3d   %3d   %3d\n",dtptr->costs[1][2],
	 dtptr->costs[2][2],dtptr->costs[3][2]);
  printf("     3|  %3d   %3d   %3d\n",dtptr->costs[1][3],
	 dtptr->costs[2][3],dtptr->costs[3][3]);
}

linkhandler0(linkid, newcost)   
  int linkid, newcost;

/* called when cost from 0 to linkid changes from current value to newcost*/
/* You can leave this routine empty if you're an undergrad. If you want */
/* to use this routine, you'll need to change the value of the LINKCHANGE */
/* constant definition in prog3.c from 0 to 1 */
	
{
}
