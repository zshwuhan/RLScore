import numpy as np

from scipy.sparse.linalg import LinearOperator
from scipy.sparse.linalg import qmr

from rlscore.utilities import sampled_kronecker_products
from rlscore.pairwise_predictor import KernelPairwisePredictor
from rlscore.pairwise_predictor import LinearPairwisePredictor


TRAIN_LABELS = 'Y'
CALLBACK_FUNCTION = 'callback'
        

def func(v, X1, X2, Y, rowind, colind, lamb):
    P = sampled_kronecker_products.sampled_vec_trick(v, X2, X1, colind, rowind)
    z = (1. - Y*P)
    #print z
    z = np.where(z>0, z, 0)
    #return np.dot(z,z)
    return 0.5*(np.dot(z,z)+lamb*np.dot(v,v))

def gradient(v, X1, X2, Y, rowind, colind, lamb):
    P = sampled_kronecker_products.sampled_vec_trick(v, X2, X1, colind, rowind)
    z = (1. - Y*P)
    z = np.where(z>0, z, 0)
    sv = np.nonzero(z)[0]
    rows = rowind[sv]
    cols = colind[sv]
    A = - sampled_kronecker_products.sampled_vec_trick(Y[sv], X2.T, X1.T, None, None, cols, rows)
    B = sampled_kronecker_products.sampled_vec_trick(P[sv], X2.T, X1.T, None, None, cols, rows)
    return A + B + lamb*v

def hessian(v, p, X1, X2, Y, rowind, colind, lamb):
    P = sampled_kronecker_products.sampled_vec_trick(v, X2, X1, colind, rowind)
    z = (1. - Y*P)
    z = np.where(z>0, z, 0)
    sv = np.nonzero(z)[0]
    rows = rowind[sv]
    cols = colind[sv]
    p_after = sampled_kronecker_products.sampled_vec_trick(p, X2, X1, cols, rows)
    p_after = sampled_kronecker_products.sampled_vec_trick(p_after, X2.T, X1.T, None, None, cols, rows)
    return p_after + lamb*p    

class KronSVM(object):
        
    
    def __init__(self, **kwargs):
        self.resource_pool = kwargs
        Y = kwargs[TRAIN_LABELS]
        self.label_row_inds = np.array(kwargs["label_row_inds"], dtype = np.int32)
        self.label_col_inds = np.array(kwargs["label_col_inds"], dtype = np.int32)
        self.Y = Y
        self.trained = False
        if kwargs.has_key("regparam"):
            self.regparam = kwargs["regparam"]
        else:
            self.regparam = 1.0
        if kwargs.has_key(CALLBACK_FUNCTION):
            self.callbackfun = kwargs[CALLBACK_FUNCTION]
        else:
            self.callbackfun = None
        if kwargs.has_key("compute_risk"):
            self.compute_risk = kwargs["compute_risk"]
        else:
            self.compute_risk = False
        self.train()
    
    
    def train(self):
        if self.resource_pool.has_key('kmatrix1'):
            self.solve_kernel(self.regparam)
        else:
            self.solve_linear(self.regparam)

    def solve_linear(self, regparam):
        self.regparam = regparam
        X1 = self.resource_pool['xmatrix1']
        X2 = self.resource_pool['xmatrix2']
        self.X1, self.X2 = X1, X2
        
        if 'maxiter' in self.resource_pool: maxiter = int(self.resource_pool['maxiter'])
        else: maxiter = 1000

        if 'inneriter' in self.resource_pool: inneriter = int(self.resource_pool['inneriter'])
        else: inneriter = 50
        
        x1tsize, x1fsize = X1.shape #m, d
        x2tsize, x2fsize = X2.shape #q, r
        
        label_row_inds = np.array(self.label_row_inds, dtype = np.int32)
        label_col_inds = np.array(self.label_col_inds, dtype = np.int32)
        


        Y = self.Y
        rowind = label_row_inds
        colind = label_col_inds
        lamb = self.regparam
        rowind = np.array(rowind, dtype = np.int32)
        colind = np.array(colind, dtype = np.int32)
        fdim = X1.shape[1]*X2.shape[1]
        w = np.zeros(fdim)
        #np.random.seed(1)
        #w = np.random.random(fdim)
        self.bestloss = float("inf")
        def mv(v):
            return hessian(w, v, X1, X2, Y, rowind, colind, lamb)
            
        for i in range(maxiter):
            g = gradient(w, X1, X2, Y, rowind, colind, lamb)
            G = LinearOperator((fdim, fdim), matvec=mv, rmatvec=mv, dtype=np.float64)
            self.best_residual = float("inf")
            self.w_new = None
            self.w_new = qmr(G, g, maxiter=inneriter)[0]
            if np.all(w == w - self.w_new):
                break
            w = w - self.w_new
            if self.compute_risk:
                P = sampled_kronecker_products.sampled_vec_trick(w, X1, X2, rowind, colind)
                z = (1. - Y*P)
                z = np.where(z>0, z, 0)
                loss = 0.5*(np.dot(z,z)+lamb*np.dot(w,w))
                if loss < self.bestloss:
                    self.W = w.reshape((x1fsize, x2fsize), order='F')
                    self.bestloss = loss
            else:
                self.W = w.reshape((x1fsize, x2fsize), order='F')             
            if self.callbackfun != None:
                self.callbackfun.callback(self)
        self.predictor = LinearPairwisePredictor(self.W)

    def solve_kernel(self, regparam):
        self.regparam = regparam
        K1 = self.resource_pool['kmatrix1']
        K2 = self.resource_pool['kmatrix2']
        if 'maxiter' in self.resource_pool: maxiter = int(self.resource_pool['maxiter'])
        else: maxiter = 100
        if 'inneriter' in self.resource_pool: inneriter = int(self.resource_pool['inneriter'])
        else: inneriter = 1000
        
        label_row_inds = np.array(self.label_row_inds, dtype = np.int32)
        label_col_inds = np.array(self.label_col_inds, dtype = np.int32)
        
        Y = self.Y
        rowind = label_row_inds
        colind = label_col_inds
        lamb = self.regparam
        rowind = np.array(rowind, dtype = np.int32)
        colind = np.array(colind, dtype = np.int32)
        ddim = len(rowind)
        a = np.zeros(ddim)
        self.bestloss = float("inf")
        def func(a):
            #REPLACE
            #P = np.dot(X,v)
            P =  sampled_kronecker_products.sampled_vec_trick(a, K2, K1, colind, rowind, colind, rowind)
            z = (1. - Y*P)
            z = np.where(z>0, z, 0)
            Ka = sampled_kronecker_products.sampled_vec_trick(a, K2, K1, colind, rowind, colind, rowind)
            return 0.5*(np.dot(z,z)+lamb*np.dot(a, Ka))
        def mv(v):
            rows = rowind[sv]
            cols = colind[sv]
            p = np.zeros(len(rowind))
            A =  sampled_kronecker_products.sampled_vec_trick(v, K2, K1, cols, rows, colind, rowind)
            p[sv] = A
            return p + lamb * v
        def rv(v):
            rows = rowind[sv]
            cols = colind[sv]
            p = sampled_kronecker_products.sampled_vec_trick(v[sv], K2, K1, colind, rowind, cols, rows)
            return p + lamb * v
        for i in range(maxiter):
            P =  sampled_kronecker_products.sampled_vec_trick(a, K2, K1, colind, rowind, colind, rowind)
            z = (1. - Y*P)
            z = np.where(z>0, z, 0)
            sv = np.nonzero(z)[0]
            #print "support vectors", len(sv)
            B = np.zeros(P.shape)
            B[sv] = P[sv]-Y[sv]
            B = B + lamb*a
            #solve Ax = B
            A = LinearOperator((ddim, ddim), matvec=mv, rmatvec=rv, dtype=np.float64)
            self.a_new = qmr(A, B, maxiter=inneriter)[0]
            if np.all(a == a - self.a_new):
                break
            a = a - self.a_new
            if self.compute_risk:
                loss = func(a)
                if loss < self.bestloss:
                    self.A = a
                    self.bestloss = loss
            else:
                self.A = a
            self.dual_model = KernelPairwisePredictor(a, rowind, colind)
            if self.callbackfun != None:
                self.callbackfun.callback(self)
        self.predictor = KernelPairwisePredictor(a, rowind, colind)
        if self.callbackfun != None:
            self.callbackfun.finished(self)
